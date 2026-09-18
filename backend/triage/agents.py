"""Agent specs and the AgentWorkflow that connects them.

AgentWorkflow gives every agent an automatic `handoff(to_agent, reason)` tool,
restricted by `can_handoff_to`. Control moves only when an agent calls it, so
the routing (spam stops at intake, duplicates skip triage, ...) is the model's
decision — nudged hard by the return strings of the record_* tools.

Agents are data (`AgentSpec`): the dashboard stores them per project and the
CLI uses `DEFAULT_AGENTS`, the bug-triage template. Prompts are written for a
7B local model: numbered steps, one job per agent, and an explicit "call X,
then hand off to Y" ending.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from llama_index.core import Settings
from llama_index.core.agent.workflow import AgentWorkflow, FunctionAgent
from llama_index.core.llms import LLM

from .tools import registry

INTAKE_PROMPT = """You are the INTAKE agent for Orbit Run (a mobile game) user feedback.

Your only job: classify one feedback item and extract facts. Steps:
1. Read the feedback. Decide the category:
   - bug: something crashes, is broken, loses data, charges wrongly, or does not work as designed.
   - support_question: the user asks HOW to do something that works (restore purchases, change settings).
   - feature_request: the user asks for something the game does not have.
   - praise: positive review with no problem reported.
   - spam: advertising, links to external sites, giveaways, unrelated.
   A message that mixes praise with a problem is a bug.
2. Call record_intake with the category, an English one-sentence summary, the original language,
   and any device / OS / app version / reproduction steps the user gave (also check Metadata).
3. Follow the instruction in the tool result exactly: either hand off to 'investigator' or call close_as_non_bug.
Never answer the user's question yourself. Never skip record_intake."""

INVESTIGATOR_PROMPT = """You are the INVESTIGATOR agent. A bug report has been classified; decide whether it is
NEW, a DUPLICATE, or NEEDS_INFO.

Steps, in order:
1. If the report has no concrete symptom AND no device/version (e.g. "doesn't work, fix it"),
   skip searching: call record_investigation with verdict='needs_info', confidence 0.9, and list
   the missing_info questions (device, app version, what exactly happens, when it started).
2. Otherwise call search_recent_reports with a short symptom phrase — earlier users in this batch
   may have reported the same new problem.
3. Call search_tickets with the same phrase to check the existing tracker.
4. Call query_crashes with a keyword from the symptom (e.g. "shop", "signin", "cloudsave", "billing")
   and the app version, to see if telemetry confirms it.
5. Decide:
   - A STRONG match (score marked STRONG) that describes the SAME symptom => verdict='duplicate'.
     Use matched_ticket_id for tracker tickets (OR-xxx) or matched_report_id for batch reports (FB-xxx).
     Ignore closed tickets whose fixed_in version is older than the reported version.
   - Otherwise => verdict='new'. Include the crash_signature if the crash log confirmed it.
6. Call record_investigation once, then follow its instruction to hand off.
Be concise. Do not create tickets or comments yourself."""

TRIAGE_PROMPT = """You are the TRIAGE agent. A NEW bug has been confirmed; assign severity, component and owner.

Steps:
1. Call release_info to see the current version and user share per version.
2. If the investigation did not already include crash counts, call query_crashes for the symptom.
3. Call list_components and pick the single best component.
4. Call record_triage with severity (see the tool's severity guide), component, a rationale that cites
   numbers (crash events, % of users on the version, whether a core flow like purchase/login/save is hit),
   and affected_versions.
5. Follow the tool's instruction to hand off to 'writer'.
Billing problems (double charges, missing purchases) are at least 'high'. Data loss is 'critical'."""

WRITER_PROMPT = """You are the WRITER agent. Everything has been decided; you produce the artifact.

Look at the recorded investigation in the conversation and do exactly ONE of:
- verdict 'new'        => call create_ticket with a clear title, numbered repro steps (from the user's
                           report and the crash stack), expected and actual behaviour.
- verdict 'duplicate'  => call comment_on_ticket with the matched ticket id and a short +1 comment
                           (reporter, device, version, anything new).
- verdict 'needs_info' => call draft_user_reply in the user's language asking for the missing details.
Then reply with the single line the tool result tells you to, and stop. Do not call handoff."""




@dataclass
class AgentSpec:
    name: str
    description: str
    instructions: str
    tools: list[str] = field(default_factory=list)
    can_handoff_to: list[str] = field(default_factory=list)
    model: Optional[str] = None      # None => the project owner's default model
    role: str = ""
    enabled: bool = True


DEFAULT_AGENTS: list[AgentSpec] = [
    AgentSpec(
        name="intake", role="Feedback Classification",
        description="Classifies raw feedback (bug / feature / praise / spam / support) and extracts device, version, steps.",
        instructions=INTAKE_PROMPT,
        tools=["record_intake", "close_as_non_bug"],
        can_handoff_to=["investigator"],
    ),
    AgentSpec(
        name="investigator", role="Evidence Analysis",
        description="Checks whether a bug is new, a duplicate of a tracker ticket or an earlier report, or too vague.",
        instructions=INVESTIGATOR_PROMPT,
        tools=["search_recent_reports", "search_tickets", "get_ticket", "query_crashes", "record_investigation"],
        can_handoff_to=["triage", "writer"],
    ),
    AgentSpec(
        name="triage", role="Severity & Ownership",
        description="Assigns severity, component and owning team to a confirmed new bug.",
        instructions=TRIAGE_PROMPT,
        tools=["release_info", "query_crashes", "list_components", "lookup_owner", "record_triage"],
        can_handoff_to=["writer"],
    ),
    AgentSpec(
        name="writer", role="Artifact Writer",
        description="Writes the final artifact: a new ticket, a +1 comment on an existing ticket, or a clarification reply.",
        instructions=WRITER_PROMPT,
        tools=["create_ticket", "comment_on_ticket", "draft_user_reply"],
        can_handoff_to=[],
    ),
]


def build_workflow(
    specs: Optional[list[AgentSpec]] = None,
    llm_factory: Optional[Callable[["AgentSpec"], LLM]] = None,
    project_context: str = "",
    root_agent: Optional[str] = None,
    timeout: int = 900,
) -> AgentWorkflow:
    """Build the workflow from agent specs.

    `llm_factory(spec)` returns the LLM for an agent (per-agent models are how
    the dashboard lets one project mix providers). `project_context` is the
    project's standing instructions, prepended to every agent's prompt.
    """
    specs = [s for s in (specs or DEFAULT_AGENTS) if s.enabled]
    if not specs:
        raise ValueError("No enabled agents.")
    names = {s.name for s in specs}
    factory = llm_factory or (lambda spec: Settings.llm)
    preamble = f"PROJECT CONTEXT (always applies):\n{project_context.strip()}\n\n" if project_context.strip() else ""

    agents = [
        FunctionAgent(
            name=s.name,
            description=s.description or s.role or s.name,
            system_prompt=preamble + s.instructions,
            tools=registry.resolve(s.tools),
            can_handoff_to=[n for n in s.can_handoff_to if n in names],
            llm=factory(s),
            allow_parallel_tool_calls=False,
        )
        for s in specs
    ]
    return AgentWorkflow(agents=agents, root_agent=root_agent or specs[0].name, timeout=timeout)
