"""Tool registry: the names agents can be configured with, and what they map to.

The dashboard's agent editor shows this list; `build_workflow` resolves the
names an agent row lists back to functions. Adding a tool = adding a row here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import crashes, intake, knowledge, output, ownership, tracker


@dataclass(frozen=True)
class ToolInfo:
    name: str
    fn: Callable
    category: str      # intake | investigation | triage | output
    summary: str
    side_effects: bool = False
    gated: bool = False  # can pause for human approval


_ALL = [
    ToolInfo("record_intake", intake.record_intake, "intake", "Record the classification and extracted facts of a report."),
    ToolInfo("close_as_non_bug", output.close_as_non_bug, "output", "Close praise / spam / feature / support items.", side_effects=True),
    ToolInfo("search_recent_reports", tracker.search_recent_reports, "investigation", "Search reports already processed in this project (batch memory)."),
    ToolInfo("search_tickets", tracker.search_tickets, "investigation", "Vector search over the project's ticket tracker."),
    ToolInfo("get_ticket", tracker.get_ticket, "investigation", "Fetch one tracker ticket by id."),
    ToolInfo("query_crashes", crashes.query_crashes, "investigation", "Aggregate the project's crash telemetry by signature."),
    ToolInfo("search_knowledge", knowledge.search_knowledge, "investigation", "Search uploaded documents, URLs and notes in the project knowledge base."),
    ToolInfo("record_investigation", tracker.record_investigation, "investigation", "Record new / duplicate / needs_info with a guarded duplicate claim."),
    ToolInfo("release_info", ownership.release_info, "triage", "Current version, user share per version, next release."),
    ToolInfo("list_components", ownership.list_components, "triage", "Valid components and owning teams."),
    ToolInfo("lookup_owner", ownership.lookup_owner, "triage", "Owning team for a component."),
    ToolInfo("record_triage", ownership.record_triage, "triage", "Record severity, component and owner."),
    ToolInfo("create_ticket", output.create_ticket, "output", "Write a new ticket; pauses for human approval when severity or confidence trips the gate.", side_effects=True, gated=True),
    ToolInfo("comment_on_ticket", output.comment_on_ticket, "output", "Add a +1 comment to an existing ticket.", side_effects=True),
    ToolInfo("draft_user_reply", output.draft_user_reply, "output", "Draft a clarification reply to the user.", side_effects=True),
]

TOOLS: dict[str, ToolInfo] = {t.name: t for t in _ALL}


def resolve(names: list[str]) -> list[Callable]:
    unknown = [n for n in names if n not in TOOLS]
    if unknown:
        raise ValueError(f"Unknown tools: {', '.join(unknown)}")
    return [TOOLS[n].fn for n in names]


def describe() -> list[dict]:
    return [
        {"name": t.name, "category": t.category, "summary": t.summary, "side_effects": t.side_effects, "gated": t.gated}
        for t in _ALL
    ]
