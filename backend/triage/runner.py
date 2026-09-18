"""Run the workflow on one feedback item and stream what happens.

`workflow.run()` returns a handler; iterating `handler.stream_events()` yields
agent switches, tool calls, tool results, text deltas — and InputRequiredEvent
when a tool has paused for a human. We answer that by sending a
HumanResponseEvent back into the same context.

The runner is engine-only: it knows nothing about the database or the
dashboard. The CLI and the server both drive it through `on_event` (sync) and
`ask_human` (async).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional, Union

from llama_index.core.agent.workflow import AgentInput, AgentOutput, AgentStream, ToolCall, ToolCallResult
from llama_index.core.agent.workflow import AgentWorkflow
from workflows import Context
from workflows.events import HumanResponseEvent, InputRequiredEvent

from . import settings
from .runtime import ProjectRuntime
from .schemas import RawFeedback, Result
from .state import initial_state

AskHuman = Callable[[str], Union[str, Awaitable[str]]]


@dataclass
class RunLog:
    feedback_id: str
    agents_visited: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    handoffs: int = 0
    human_gate: bool = False
    seconds: float = 0.0
    final_text: str = ""
    error: Optional[str] = None


def load_inbox(only: Optional[list[str]] = None) -> list[RawFeedback]:
    items = [RawFeedback(**json.loads(p.read_text())) for p in sorted(settings.INBOX_DIR.glob("*.json"))]
    if only:
        wanted = {o.upper() for o in only}
        items = [i for i in items if i.id.upper() in wanted]
    return items


class Runner:
    def __init__(
        self,
        workflow: AgentWorkflow,
        runtime: ProjectRuntime,
        auto_approve: bool,
        on_event: Callable,
        ask_human: AskHuman,
        extra_state: Optional[dict] = None,
    ):
        self.workflow = workflow
        self.runtime = runtime
        self.auto_approve = auto_approve
        self.on_event = on_event
        self.ask_human = ask_human
        self.extra_state = extra_state or {}   # e.g. per-project gate thresholds

    async def _ask(self, prompt: str) -> str:
        res = self.ask_human(prompt)
        if inspect.isawaitable(res):
            res = await res
        return res

    async def run_one(self, fb: RawFeedback, cancel: Optional[asyncio.Event] = None) -> tuple[Result, RunLog]:
        log = RunLog(feedback_id=fb.id)
        t0 = time.perf_counter()

        # Fresh context per item => fresh memory + fresh shared state.
        ctx = Context(self.workflow)
        await ctx.store.set("state", {**initial_state(fb.model_dump(), self.auto_approve, self.runtime.project_id), **self.extra_state})
        handler = self.workflow.run(user_msg=fb.as_prompt(), ctx=ctx)

        current_agent = None
        try:
            async for ev in handler.stream_events():
                if cancel is not None and cancel.is_set():
                    await handler.cancel_run()
                    raise RuntimeError("cancelled")
                if isinstance(ev, AgentInput) and ev.current_agent_name != current_agent:
                    if current_agent is not None:
                        log.handoffs += 1
                        self.on_event("handoff", (current_agent, ev.current_agent_name))
                    current_agent = ev.current_agent_name
                    log.agents_visited.append(current_agent)
                    self.on_event("agent", current_agent)
                elif isinstance(ev, ToolCall):
                    log.tool_calls.append(ev.tool_name)
                    self.on_event("tool_call", ev)
                elif isinstance(ev, ToolCallResult):
                    self.on_event("tool_result", ev)
                elif isinstance(ev, AgentStream):
                    self.on_event("stream", ev)
                elif isinstance(ev, AgentOutput):
                    self.on_event("agent_output", ev)
                elif isinstance(ev, InputRequiredEvent):
                    log.human_gate = True
                    self.on_event("human_gate", ev.prefix)
                    answer = await self._ask(ev.prefix)
                    self.on_event("human_answer", answer)
                    handler.ctx.send_event(HumanResponseEvent(response=answer))
            final = await handler
            log.final_text = str(final).strip()
            self.on_event("final", log.final_text)
        except Exception as exc:  # keep the batch going; the caller records the failure
            log.error = f"{type(exc).__name__}: {exc}"
            self.on_event("error", log.error)

        log.seconds = time.perf_counter() - t0
        state = await ctx.store.get("state")
        result = self._to_result(fb, state)

        # Let later items in this project find this one.
        intake = state.get("intake") or {}
        async with self.runtime.lock:
            self.runtime.remember_report(
                fb.id, text=f"{intake.get('summary', '')}\n{fb.text}", outcome=result.outcome,
                # A duplicate remembers the ticket it resolved to, so a chain of
                # duplicates (FB-003 -> FB-002 -> FB-001) still lands on the ticket.
                ticket_id=result.ticket_id or result.duplicate_of,
            )
        return result, log

    @staticmethod
    def _to_result(fb: RawFeedback, state: dict) -> Result:
        intake = state.get("intake") or {}
        inv = state.get("investigation") or {}
        tri = state.get("triage") or {}
        # No output tool ran => the agents stopped early; say so instead of guessing.
        outcome = state.get("outcome") or "unresolved"
        return Result(
            feedback_id=fb.id,
            outcome=outcome,
            category=intake.get("category") or "other",
            verdict=inv.get("verdict"),
            severity=tri.get("severity"),
            component=tri.get("component"),
            duplicate_of=state.get("ticket_id") if outcome == "duplicate" else None,
            ticket_id=state.get("ticket_id") if outcome == "new_ticket" else None,
            artifact=state.get("artifact"),
        )
