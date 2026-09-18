"""Writer agent tools: the only tools with side effects (artifacts in the project's out dir).

`create_ticket` also holds the human gate. It is enforced in code, not in the
prompt: if severity or confidence trips the threshold, the tool itself pauses
the workflow with `ctx.wait_for_event(HumanResponseEvent, ...)` and does not
write anything until a person answers. The model cannot skip it.
"""


from typing import Optional

from workflows import Context
from workflows.events import HumanResponseEvent, InputRequiredEvent

from .. import runtime, settings
from ..schemas import Ticket
from ..state import get_state, update_state
from .coerce import StrList, as_list


async def _needs_human(state: dict) -> Optional[str]:
    if state.get("auto_approve"):
        return None
    gate = state.get("gate") or {}
    severities = set(gate.get("severities") or settings.GATE_SEVERITIES)
    min_conf = float(gate.get("min_confidence", settings.GATE_MIN_CONFIDENCE))
    sev = (state.get("triage") or {}).get("severity")
    conf = (state.get("investigation") or {}).get("confidence", 1.0)
    reasons = []
    if sev in severities:
        reasons.append(f"severity={sev}")
    if conf < min_conf:
        reasons.append(f"confidence={conf:.2f}")
    return ", ".join(reasons) or None


async def create_ticket(
    ctx: Context,
    title: str,
    repro_steps: StrList,
    expected: str,
    actual: str,
) -> str:
    """Create a new engineering ticket for a NEW, triaged bug. Call exactly once.

    Severity, component, owner and evidence are taken from the recorded triage and
    investigation — you only write the human-readable parts.

    Args:
        title: short imperative title, e.g. "Shop screen crashes on open in 2.4.1 (NPE in renderFeatured)".
        repro_steps: numbered steps as a list of strings.
        expected: what should happen.
        actual: what happens instead.
    """
    state = await get_state(ctx)
    rt = runtime.for_state(state)
    tri, inv, intake, fb = state.get("triage"), state.get("investigation"), state.get("intake"), state["feedback"]
    if not tri or not inv:
        return "Cannot create a ticket: triage or investigation missing. This should have been recorded earlier."

    gate = await _needs_human(state)
    approved_by = "auto"
    if gate:
        summary = (
            f"[HUMAN GATE — {gate}]\n"
            f"Proposed ticket: {title}\n"
            f"  severity={tri['severity']} component={tri['component']} owner={tri['owner']}\n"
            f"  evidence: {inv['evidence']}\n"
            f"  from feedback {fb['id']} ({fb['source']})\n"
            "Approve? [y]es / [n]o / or type a corrected severity (low|medium|high|critical): "
        )
        if state.get("preapproved"):
            # A human already decided on an earlier attempt of this item (the run was
            # interrupted while waiting); apply that decision instead of asking again.
            answer = str(state["preapproved"]).strip().lower()
        else:
            reply = await ctx.wait_for_event(
                HumanResponseEvent,
                waiter_id=f"approve-{fb['id']}",
                waiter_event=InputRequiredEvent(prefix=summary),
            )
            answer = (reply.response or "").strip().lower()
        if answer in ("n", "no"):
            await update_state(ctx, outcome="dropped", artifact=None)
            return "Human REJECTED the ticket. Reply to the user with: 'Ticket rejected by reviewer.' and stop."
        if answer in ("low", "medium", "high", "critical"):
            tri["severity"] = answer
            await update_state(ctx, triage=tri)
        approved_by = "human"

    ticket_id = await rt.allocate_ticket_id()
    ticket = Ticket(
        id=ticket_id, title=title, severity=tri["severity"], component=tri["component"], owner=tri["owner"],
        affected_versions=tri.get("affected_versions") or ([intake["app_version"]] if intake and intake.get("app_version") else []),
        repro_steps=as_list(repro_steps), expected=expected, actual=actual,
        evidence=inv["evidence"] + (f" Crash signature: {inv['crash_signature']}." if inv.get("crash_signature") else ""),
        source_feedback=[fb["id"]], approved_by=approved_by,
    )
    md = (
        f"# {ticket.id}: {ticket.title}\n\n"
        f"**Severity:** {ticket.severity}  **Component:** {ticket.component}  **Owner:** {ticket.owner}  "
        f"**Versions:** {', '.join(ticket.affected_versions) or 'unknown'}  **Approved by:** {ticket.approved_by}\n\n"
        "## Steps to reproduce\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(ticket.repro_steps, 1)) + "\n\n"
        f"## Expected\n{ticket.expected}\n\n## Actual\n{ticket.actual}\n\n"
        f"## Evidence\n{ticket.evidence}\n\n## Source feedback\n{', '.join(ticket.source_feedback)}\n"
    )
    path = await rt.write_artifact("tickets", ticket.id, ticket.model_dump(), md, state.get("run_id"))
    rt.register_ticket(ticket.model_dump())
    await update_state(ctx, outcome="new_ticket", artifact=path, ticket_id=ticket.id)
    return f"Created {ticket.id} at {path}. Reply to the user with one line: 'Created {ticket.id} ({ticket.severity}, {ticket.owner}).' and stop."


async def comment_on_ticket(ctx: Context, ticket_id: str, comment: str) -> str:
    """Add a '+1' comment with new evidence to an EXISTING ticket for a duplicate report.

    Args:
        ticket_id: the ticket this report duplicates (from the investigation), e.g. "OR-104".
        comment: 2-4 sentences: who reported, device/version, anything new vs the ticket.
    """
    state = await get_state(ctx)
    rt = runtime.for_state(state)
    fb = state["feedback"]
    tid = ticket_id.strip().upper()
    if not tid.startswith(f"{rt.ticket_prefix}-"):
        resolved = (state.get("investigation") or {}).get("matched_ticket_id")
        if resolved:
            tid = resolved
        else:
            return (
                f"'{ticket_id}' is a feedback id, not a ticket. The investigation found no tracker ticket "
                "for this duplicate; call comment_on_ticket again with the ticket id (OR-xxx) from the "
                "investigation, or if there is none, call draft_user_reply to acknowledge the report."
            )
    payload = {"ticket_id": tid, "feedback_id": fb["id"], "comment": comment}
    md = f"# Comment on {tid}\n\n_From feedback {fb['id']} ({fb['source']}, {fb['author']})_\n\n{comment}\n"
    path = await rt.write_artifact("comments", f"{tid}__{fb['id']}", payload, md, state.get("run_id"))
    await update_state(ctx, outcome="duplicate", artifact=path, ticket_id=tid)
    return f"Comment added to {tid} at {path}. Reply to the user with one line: 'Duplicate of {tid}, comment added.' and stop."


async def draft_user_reply(ctx: Context, reply: str) -> str:
    """Draft a reply asking the user for the information needed to act on a vague report.

    Args:
        reply: the full reply text, friendly and short, in the user's language,
            asking for the specific missing details (device, version, what exactly happens).
    """
    state = await get_state(ctx)
    rt = runtime.for_state(state)
    fb = state["feedback"]
    payload = {"feedback_id": fb["id"], "to": fb["author"], "reply": reply}
    md = f"# Reply to {fb['author']} ({fb['id']}, {fb['source']})\n\n{reply}\n"
    path = await rt.write_artifact("replies", fb["id"], payload, md, state.get("run_id"))
    await update_state(ctx, outcome="needs_info", artifact=path)
    return f"Reply drafted at {path}. Reply to the user with one line: 'Clarification requested.' and stop."


async def close_as_non_bug(ctx: Context, reason: str) -> str:
    """Close a feedback item that is not a bug (praise, spam, feature request, support question).

    Args:
        reason: one short sentence, e.g. "5-star praise, no action" or "spam link".
    """
    state = await get_state(ctx)
    rt = runtime.for_state(state)
    fb, intake = state["feedback"], state.get("intake") or {}
    payload = {"feedback_id": fb["id"], "category": intake.get("category"), "reason": reason}
    md = f"# Dropped {fb['id']}\n\n**Category:** {intake.get('category')}\n\n{reason}\n"
    path = await rt.write_artifact("dropped", fb["id"], payload, md, state.get("run_id"))
    await update_state(ctx, outcome="dropped", artifact=path)
    return f"Closed as {intake.get('category')}. Reply to the user with one line: 'Not a bug ({intake.get('category')}).' and stop."
