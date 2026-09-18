"""Tests for the deterministic half of the system — no LLM involved.

Every test builds a `ProjectRuntime` without vector indexes (or with a stub)
and registers it under a project id the workflow state points at, which is
exactly how the server isolates projects.

Embedding-backed tests need Ollama running with nomic-embed-text; they are
skipped automatically if it isn't reachable.
"""

import asyncio
import json
import urllib.request

import pytest
from workflows import Context, Workflow, step
from workflows.events import HumanResponseEvent, InputRequiredEvent, StartEvent, StopEvent

from triage import runtime, settings
from triage.runtime import ProjectRuntime
from triage.state import initial_state
from triage.tools import coerce, crashes, output, ownership, tracker

PID = "test-project"


from llama_index.core.embeddings import MockEmbedding


def _NoEmbed():
    """Deterministic stand-in embed model: index plumbing works, no Ollama needed."""
    return MockEmbedding(embed_dim=8)


def _ollama_up() -> bool:
    try:
        urllib.request.urlopen(f"{settings.OLLAMA_URL}/api/version", timeout=1)
        return True
    except Exception:
        return False


@pytest.fixture
def rt(tmp_path):
    """Fixture-backed runtime, no indexes, registered as PID."""
    r = ProjectRuntime.from_fixtures(PID, settings.FIXTURES_DIR, _NoEmbed(), out_dir=tmp_path, index_tickets=False)
    runtime.register(r)
    yield r
    runtime.unregister(PID)


async def _run_tool_async(call, state):
    """Run one tool call inside a real Workflow so ctx / wait_for_event work."""

    class W(Workflow):
        @step
        async def go(self, ctx: Context, ev: StartEvent) -> StopEvent:
            await ctx.store.set("state", state)
            return StopEvent(result=(await call(ctx), await ctx.store.get("state")))

    return await W(timeout=10).run()


def _run_tool(call, state):
    return asyncio.run(_run_tool_async(call, state))


def _base_state(auto=True, **extra):
    s = initial_state({"id": "FB-T", "source": "test", "author": "a", "text": "t"}, auto, PID)
    s.update(extra)
    return s


# ---------------------------------------------------------------- coerce ----

@pytest.mark.parametrize("raw,expected", [
    ('["a", "b"]', ["a", "b"]),
    ("a; b", ["a", "b"]),
    ("1. open shop 2. tap icon 3. crash", ["open shop", "tap icon", "crash"]),
    (["x", " y "], ["x", "y"]),
    (None, []),
    ("null", []),
    ("single step", ["single step"]),
])
def test_as_list(raw, expected):
    assert coerce.as_list(raw) == expected


def test_as_float():
    assert coerce.as_float("0.8") == 0.8
    assert coerce.as_float("high", default=0.5) == 0.5


# --------------------------------------------------------------- crashes ----

def test_query_crashes_groups_by_signature(rt):
    out = crashes.aggregate(rt.crash_rows, "shop", "2.4.1")
    assert "NPE:ShopScreen.renderFeatured" in out
    assert "events=28" in out
    assert "'Android': 19" in out and "'iOS': 9" in out


def test_query_crashes_no_match(rt):
    assert "No crashes match" in crashes.aggregate(rt.crash_rows, "teleport", "9.9.9")


def test_query_crashes_tool_uses_project_runtime(rt):
    msg, _ = _run_tool(lambda ctx: crashes.query_crashes(ctx, "shop", "2.4.1"), _base_state())
    assert "events=28" in msg


# ------------------------------------------------------------- ownership ----

def test_lookup_owner(rt):
    assert "team-monetization" in _run_tool(lambda ctx: ownership.lookup_owner(ctx, "billing"), _base_state())[0]
    assert "Unknown component" in _run_tool(lambda ctx: ownership.lookup_owner(ctx, "kitchen"), _base_state())[0]


def test_record_triage_rejects_bad_component(rt):
    msg, _ = _run_tool(lambda ctx: ownership.record_triage(ctx, "high", "kitchen", "r"), _base_state())
    assert "Unknown component" in msg


# ------------------------------------------------------------ human gate ----

class _GateWorkflow:
    """Run create_ticket inside a real Workflow so wait_for_event works."""

    def __init__(self, state):
        class W(Workflow):
            @step
            async def go(self, ctx: Context, ev: StartEvent) -> StopEvent:
                await ctx.store.set("state", state)
                msg = await output.create_ticket(ctx, "T", ["s1"], "exp", "act")
                return StopEvent(result=(msg, await ctx.store.get("state")))

        self.wf = W(timeout=30)

    def run(self, answer: str | None):
        async def go():
            handler = self.wf.run()
            async for ev in handler.stream_events():
                if isinstance(ev, InputRequiredEvent):
                    assert answer is not None, "gate fired unexpectedly"
                    handler.ctx.send_event(HumanResponseEvent(response=answer))
            return await handler
        return asyncio.run(go())


def _state(severity, confidence, auto=False):
    return _base_state(
        auto,
        intake={"category": "bug", "summary": "s", "app_version": "2.4.1"},
        investigation={"verdict": "new", "evidence": "e", "confidence": confidence},
        triage={"severity": severity, "component": "shop", "owner": "team-monetization", "rationale": "r", "affected_versions": ["2.4.1"]},
    )


def test_low_severity_skips_gate(rt, tmp_path):
    msg, state = _GateWorkflow(_state("low", 0.9)).run(answer=None)
    assert state["outcome"] == "new_ticket" and "Created OR-" in msg
    assert json.loads((tmp_path / "tickets" / f"{state['ticket_id']}.json").read_text())["approved_by"] == "auto"


def test_high_severity_waits_and_accepts_override(rt, tmp_path):
    msg, state = _GateWorkflow(_state("high", 0.9)).run(answer="critical")
    assert state["outcome"] == "new_ticket" and state["triage"]["severity"] == "critical"
    assert json.loads((tmp_path / "tickets" / f"{state['ticket_id']}.json").read_text())["approved_by"] == "human"


def test_low_confidence_triggers_gate_and_rejection(rt, tmp_path):
    msg, state = _GateWorkflow(_state("low", 0.4)).run(answer="n")
    assert state["outcome"] == "dropped" and "REJECTED" in msg
    assert not list((tmp_path / "tickets").glob("*.json"))


def test_auto_approve_bypasses_gate(rt):
    msg, state = _GateWorkflow(_state("critical", 0.1, auto=True)).run(answer=None)
    assert state["outcome"] == "new_ticket"


def test_artifact_hook_is_called(rt):
    seen = []
    rt.artifact_hook = lambda sub, name, path, payload, run_id: seen.append((sub, name))
    _GateWorkflow(_state("low", 0.9)).run(answer=None)
    assert seen and seen[0][0] == "tickets"


# ----------------------------------------------------------- isolation ----

def test_two_projects_do_not_share_tickets(tmp_path):
    a = runtime.register(ProjectRuntime.from_sources("A", _NoEmbed(), tickets=[{"id": "OR-1", "title": "a", "description": ""}], out_dir=tmp_path / "a", index_tickets=False))
    b = runtime.register(ProjectRuntime.from_sources("B", _NoEmbed(), tickets=[{"id": "OR-2", "title": "b", "description": ""}], out_dir=tmp_path / "b", index_tickets=False))
    try:
        sa = initial_state({"id": "FB-T"}, True, "A")
        sb = initial_state({"id": "FB-T"}, True, "B")
        assert "OR-1" in _run_tool(lambda ctx: tracker.get_ticket(ctx, "OR-1"), sa)[0]
        assert "No ticket" in _run_tool(lambda ctx: tracker.get_ticket(ctx, "OR-2"), sa)[0]
        assert "OR-2" in _run_tool(lambda ctx: tracker.get_ticket(ctx, "OR-2"), sb)[0]
        assert a.next_ticket_num == 2 and b.next_ticket_num == 3
    finally:
        runtime.unregister("A"); runtime.unregister("B")


# --------------------------------------------------------------- tracker ----

@pytest.mark.skipif(not _ollama_up(), reason="Ollama not running")
def test_tracker_duplicate_detection_and_batch_memory(tmp_path):
    # One event loop for everything: the embedding client binds to the loop it first runs in.
    async def go():
        r = runtime.register(ProjectRuntime.from_fixtures(PID, settings.FIXTURES_DIR, settings.make_embed(), out_dir=tmp_path))
        try:
            msg, state = await _run_tool_async(lambda ctx: tracker.search_tickets(ctx, "Google sign-in returns to title screen"), _base_state())
            assert "OR-104" in msg.splitlines()[1] and "OR-104" in state["hits"]
            r.remember_report("FB-001", "Shop screen crashes on open in 2.4.1", "new_ticket", "OR-118")
            msg, _ = await _run_tool_async(lambda ctx: tracker.search_recent_reports(ctx, "crash opening the shop 2.4.1"), _base_state())
            hit = msg.splitlines()[1]
            assert "FB-001" in hit and "STRONG" in hit
        finally:
            runtime.unregister(PID)

    asyncio.run(go())


# ------------------------------------------------- duplicate claim guard ----

def _inv_state(hits, intake_version="2.4.1", intake=None):
    s = _base_state()
    s["intake"] = intake or {"category": "bug", "app_version": intake_version}
    s["hits"] = dict(hits)
    return s


def _tickets_rt(tmp_path, tickets):
    r = ProjectRuntime.from_sources(PID, _NoEmbed(), tickets=tickets, out_dir=tmp_path, index_tickets=False)
    return runtime.register(r)


def test_duplicate_claim_needs_strong_hit(tmp_path):
    _tickets_rt(tmp_path, [
        {"id": "OR-101", "status": "closed", "fixed_in": "2.3.8", "title": "", "description": ""},
        {"id": "OR-104", "status": "open", "fixed_in": None, "title": "", "description": ""},
    ])
    try:
        hits = {"OR-101": 0.60, "FB-001": 0.79}
        rec = lambda **kw: (lambda ctx: tracker.record_investigation(ctx, "duplicate", "e", 0.9, **kw))
        # weak tracker hit -> rejected
        msg, _ = _run_tool(rec(matched_ticket_id="OR-101"), _inv_state(hits))
        assert "rejected" in msg and "weak" in msg
        # never-searched ticket -> rejected
        msg, _ = _run_tool(rec(matched_ticket_id="OR-104"), _inv_state(hits))
        assert "did not appear" in msg
        # strong batch hit + hallucinated ticket -> ticket dropped, batch match kept
        msg, _ = _run_tool(rec(matched_ticket_id="OR-104", matched_report_id="FB-001"), _inv_state(hits))
        assert "Recorded investigation" in msg and '"matched_report_id":"FB-001"' in msg and '"matched_ticket_id":null' in msg
    finally:
        runtime.unregister(PID)


def test_closed_fixed_ticket_is_regression_not_duplicate(tmp_path):
    _tickets_rt(tmp_path, [{"id": "OR-101", "status": "closed", "fixed_in": "2.3.8", "title": "", "description": ""}])
    try:
        msg, _ = _run_tool(
            lambda ctx: tracker.record_investigation(ctx, "duplicate", "e", 0.9, matched_ticket_id="OR-101"),
            _inv_state({"OR-101": 0.9}),  # strong, but fixed before the reported version
        )
        assert "regression" in msg and "verdict='new'" in msg
    finally:
        runtime.unregister(PID)


def test_created_ticket_becomes_citable(tmp_path):
    r = _tickets_rt(tmp_path, [])
    try:
        r.register_ticket({"id": "OR-118", "title": "Shop crash", "severity": "high", "component": "shop",
                           "affected_versions": ["2.4.1"], "owner": "team-monetization", "actual": "App crashes"})
        msg, _ = _run_tool(
            lambda ctx: tracker.record_investigation(ctx, "duplicate", "e", 0.9, matched_ticket_id="OR-118"),
            _inv_state({"OR-118": 0.8}),
        )
        assert "Recorded investigation" in msg and '"matched_ticket_id":"OR-118"' in msg
    finally:
        runtime.unregister(PID)


def test_new_verdict_requires_actionable_details(tmp_path):
    _tickets_rt(tmp_path, [])
    try:
        def make(intake):
            return _run_tool(lambda ctx: tracker.record_investigation(ctx, "new", "e", 0.8), _inv_state({}, intake=intake))[0]
        assert "rejected" in make({"category": "bug", "summary": "laggy"})                       # nothing actionable
        assert "Recorded" in make({"category": "bug", "summary": "laggy", "device": "Pixel 8"})  # device is enough
    finally:
        runtime.unregister(PID)
