"""Helpers around the AgentWorkflow shared state.

AgentWorkflow stores a plain dict under ctx.store["state"]. Tools mutate it
through these helpers so the shape stays in one place. `project_id` is how
tools find their ProjectRuntime; `hits` is the per-item search evidence the
duplicate-claim guard checks against.
"""

from __future__ import annotations

from typing import Any

from workflows import Context


def initial_state(feedback: dict, auto_approve: bool, project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "feedback": feedback,
        "intake": None,
        "investigation": None,
        "triage": None,
        "outcome": None,        # set by the writer's output tools
        "artifact": None,
        "ticket_id": None,
        "auto_approve": auto_approve,
        "hits": {},             # candidate id -> best similarity seen by a search for this item
    }


async def get_state(ctx: Context) -> dict[str, Any]:
    return await ctx.store.get("state")


async def update_state(ctx: Context, **fields: Any) -> dict[str, Any]:
    state = await ctx.store.get("state")
    state.update(fields)
    await ctx.store.set("state", state)
    return state
