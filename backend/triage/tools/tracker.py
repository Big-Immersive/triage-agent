"""Investigator tools: search the ticket tracker and earlier reports in this batch.

Two small vector indexes per project, both LlamaIndex + local embeddings, held
on the project's `ProjectRuntime`:

  * tickets  — the project's tracker, built from its knowledge items.
  * batch    — reports already processed in this project. The runner inserts a
               node after each item, so later items can be matched to earlier
               ones (FB-002 "shop crash" -> duplicate of the ticket for FB-001).

Search evidence for the *current item* lives in `state["hits"]`, so
record_investigation only accepts duplicate claims the model actually saw.
"""


import json
from typing import Optional, Union

from llama_index.core.schema import NodeWithScore
from pydantic import ValidationError
from workflows import Context

from .. import runtime, settings
from ..schemas import Investigation
from ..state import get_state, update_state
from .coerce import StrList, as_float, as_list


def _version_tuple(v: str) -> tuple:
    return tuple(int(x) for x in v.split(".") if x.isdigit())


def _fmt(nodes: list[NodeWithScore], key: str, hits: dict[str, float]) -> list[str]:
    lines = []
    for n in nodes:
        score = n.score or 0.0
        if n.metadata.get(key):
            hits[n.metadata[key]] = max(score, hits.get(n.metadata[key], 0.0))
        # A batch hit that already resolved to a ticket is evidence for that ticket too.
        if key == "feedback_id" and n.metadata.get("ticket_id"):
            tid = n.metadata["ticket_id"]
            hits[tid] = max(score, hits.get(tid, 0.0))
        flag = "STRONG" if score >= settings.DUPLICATE_MIN_SCORE else "weak"
        meta = {k: v for k, v in n.metadata.items() if k in ("ticket_id", "status", "feedback_id", "outcome", "component")}
        text = n.get_content().replace("\n", " ")[:220]
        lines.append(f"- score={score:.2f} ({flag}) {meta}: {text}")
    return lines


async def search_tickets(ctx: Context, query: str) -> str:
    """Search the existing bug tracker for tickets similar to the report.

    Use a short description of the symptom, e.g. "crash when opening shop 2.4.1"
    or "Google sign-in returns to title screen". Returns the closest tickets with
    similarity scores; treat a match as a duplicate only if it is marked STRONG
    AND describes the same symptom.
    """
    state = await get_state(ctx)
    rt = runtime.for_state(state)
    nodes = await rt.search_tickets(query)
    lines = _fmt(nodes, "ticket_id", state["hits"])
    await update_state(ctx, hits=state["hits"])
    return "Tracker results:\n" + "\n".join(lines) if nodes else "No tickets found."


async def get_ticket(ctx: Context, ticket_id: str) -> str:
    """Fetch the full record of one tracker ticket by id, e.g. "OR-104"."""
    rt = runtime.for_state(await get_state(ctx))
    t = rt.tickets.get(ticket_id.strip().upper())
    return json.dumps(t, indent=1) if t else f"No ticket {ticket_id}."


async def search_recent_reports(ctx: Context, query: str) -> str:
    """Search feedback items already processed EARLIER IN THIS BATCH.

    Use this to detect several users reporting the same new problem. If a STRONG
    match has outcome=new_ticket, this report is a duplicate of that ticket.
    """
    state = await get_state(ctx)
    rt = runtime.for_state(state)
    nodes = await rt.search_reports(query)
    nodes = [n for n in nodes if n.metadata.get("outcome") in ("new_ticket", "duplicate")]
    lines = _fmt(nodes, "feedback_id", state["hits"])
    await update_state(ctx, hits=state["hits"])
    return "Earlier reports in this batch:\n" + "\n".join(lines) if nodes else "No earlier reports match."


def _check_duplicate_claim(inv: Investigation, tickets: dict[str, dict], hits: dict[str, float]) -> list[str]:
    """Return reasons the duplicate claim is not supported by this item's search evidence."""
    problems: list[str] = []
    if inv.matched_ticket_id:
        tid = inv.matched_ticket_id
        if tid not in tickets:
            problems.append(f"{tid} does not exist in the tracker.")
        else:
            score = hits.get(tid)
            if score is None:
                problems.append(f"{tid} did not appear in any search result for this report.")
            elif score < settings.DUPLICATE_MIN_SCORE:
                problems.append(f"{tid} scored only {score:.2f} (weak, threshold {settings.DUPLICATE_MIN_SCORE}).")
    if inv.matched_report_id:
        rid = inv.matched_report_id
        score = hits.get(rid)
        if score is None:
            problems.append(f"{rid} did not appear in search_recent_reports for this report.")
        elif score < settings.DUPLICATE_MIN_SCORE:
            problems.append(f"{rid} scored only {score:.2f} (weak, threshold {settings.DUPLICATE_MIN_SCORE}).")
    # If the batch match is good but the ticket claim is bad, keep the good half.
    if inv.matched_report_id and inv.matched_ticket_id and problems:
        rid_ok = hits.get(inv.matched_report_id, 0.0) >= settings.DUPLICATE_MIN_SCORE
        if rid_ok and all(inv.matched_ticket_id in p for p in problems):
            inv.matched_ticket_id = None
            return []
    return problems


async def record_investigation(
    ctx: Context,
    verdict: str,
    evidence: str,
    confidence: Union[float, str],
    matched_ticket_id: Optional[str] = None,
    matched_report_id: Optional[str] = None,
    crash_signature: Optional[str] = None,
    missing_info: StrList = None,
) -> str:
    """Record the investigation verdict. Call exactly once, after searching.

    Args:
        verdict: 'duplicate' if a STRONG tracker or batch match describes the same symptom;
            'needs_info' if the report is too vague to act on (no symptom, no device/version);
            otherwise 'new'.
        evidence: 1-3 sentences: what you searched, what matched, crash-log findings.
        confidence: 0.0-1.0, how sure you are of the verdict.
        matched_ticket_id: for duplicates of an existing tracker ticket, e.g. "OR-104".
        matched_report_id: for duplicates of an earlier report in this batch, e.g. "FB-001".
        crash_signature: signature from the crash log if one matches, e.g. "NPE:ShopScreen.renderFeatured".
        missing_info: for needs_info, the questions to ask the user.
    """
    try:
        inv = Investigation(
            verdict=verdict, evidence=evidence, confidence=as_float(confidence),
            matched_ticket_id=matched_ticket_id, matched_report_id=matched_report_id,
            crash_signature=crash_signature, missing_info=as_list(missing_info),
        )
    except ValidationError as exc:
        return f"Invalid investigation, fix and call again: {exc.errors()[0]['msg']} (field: {exc.errors()[0]['loc']})"

    state = await get_state(ctx)
    rt = runtime.for_state(state)
    if inv.verdict == "duplicate":
        if inv.matched_ticket_id:
            inv.matched_ticket_id = inv.matched_ticket_id.strip().upper()
        if inv.matched_report_id:
            inv.matched_report_id = inv.matched_report_id.strip().upper()
        # The model may put a batch report id in the ticket field; tolerate that.
        if inv.matched_ticket_id and inv.matched_ticket_id.startswith("FB-"):
            inv.matched_report_id, inv.matched_ticket_id = inv.matched_ticket_id, None
        if not (inv.matched_ticket_id or inv.matched_report_id):
            return "verdict=duplicate requires matched_ticket_id or matched_report_id. Fix and call again."

        problems = _check_duplicate_claim(inv, rt.tickets, state.get("hits") or {})
        if problems:
            return (
                "Duplicate claim rejected: " + " ".join(problems)
                + " Either name a candidate that was marked STRONG in your search results, "
                  "or call record_investigation again with verdict='new' — and rewrite the evidence "
                  "so it no longer claims a duplicate."
            )

    if inv.verdict == "duplicate" and inv.matched_ticket_id:
        t = rt.tickets[inv.matched_ticket_id]
        reported = (state.get("intake") or {}).get("app_version")
        if t["status"] == "closed" and t.get("fixed_in") and reported and _version_tuple(reported) > _version_tuple(t["fixed_in"]):
            return (
                f"Duplicate claim rejected: {inv.matched_ticket_id} is closed and was fixed in {t['fixed_in']}, "
                f"but this report is on {reported}. Treat it as a NEW bug (possible regression) — call "
                f"record_investigation again with verdict='new' and mention {inv.matched_ticket_id} in the evidence."
            )

    # Resolve a batch duplicate to the ticket that earlier report produced.
    if inv.verdict == "duplicate" and inv.matched_report_id and not inv.matched_ticket_id:
        resolved = rt.ticket_for_report(inv.matched_report_id.upper())
        if resolved:
            inv.matched_ticket_id = resolved

    # A "new" bug must be actionable: engineering needs at least one of device,
    # version, reproduction steps, or a confirmed crash signature to work on it.
    if inv.verdict == "new":
        intake = state.get("intake") or {}
        if not any([intake.get("app_version"), intake.get("device"), intake.get("steps"), inv.crash_signature]):
            return (
                "verdict=new rejected: the report names no device, app version or reproduction steps and no "
                "crash signature was found, so engineering cannot act on it. Call record_investigation again "
                "with verdict='needs_info' and list the missing_info to ask the user for."
            )

    await update_state(ctx, investigation=inv.model_dump())
    state = await get_state(ctx)
    nxt = {
        "new": "NOW call handoff(to_agent='triage', reason='new bug needs severity and owner').",
        "duplicate": "NOW call handoff(to_agent='writer', reason='duplicate: add +1 comment to existing ticket').",
        "needs_info": "NOW call handoff(to_agent='writer', reason='vague report: draft a clarification reply').",
    }[inv.verdict]
    return f"Recorded investigation: {inv.model_dump_json()}\n{nxt}"
