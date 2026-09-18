"""Runs: a Postgres-backed job queue executed by every API replica.

  enqueue()   -> a `runs` row with status=queued (any replica)
  worker loop -> claims queued runs with an UPDATE guarded by a per-project
                 session-level advisory lock, so runs inside one project are
                 serialized (batch memory is order-dependent: FB-002 can only
                 be a duplicate of FB-001 if FB-001 finished first) while runs
                 in different projects proceed in parallel across replicas.
  heartbeat   -> `runs.heartbeat_at` every RUN_HEARTBEAT_S; a sweeper on any
                 replica marks runs whose worker vanished as errored.

While a run executes, the engine streams events; everything that touches the
DB goes through one queue drained by one coroutine (AsyncSession is not safe
for concurrent use). The human gate parks the run on an asyncio.Future that
is resolved by an `approval.resolved` bus event — which may originate on a
different replica than the one running the workflow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import asyncpg
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from triage.agents import AgentSpec, build_workflow
from triage.runner import Runner
from triage.schemas import RawFeedback

from ..core.bus import REPLICA_ID, bus
from ..core.config import settings
from ..core.db import SessionLocal
from ..core.ids import approval_id, memory_id, run_id as new_run_id
from ..models import Agent, Approval, Memory, Project, Run, RunEvent, Task, ToolCallRow, User, UserSettings, now
from ..integrations import adapters as integrations
from . import activity, runtimes, storage, usage
from .llm import ResolvedLlmConfig, RunLlmFactory

log = logging.getLogger("triage.runs")
ACTIVE = ("queued", "running", "waiting_approval")


def _jsonable(v: Any) -> Any:
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return str(v)


def _parse_gate(prefix: str) -> dict:
    """Pull the structured bits out of create_ticket's gate prompt."""
    d: dict[str, Any] = {"prompt": prefix}
    m = re.search(r"\[HUMAN GATE — (.+?)\]", prefix)
    d["reason_raw"] = m.group(1) if m else ""
    m = re.search(r"Proposed ticket: (.+)", prefix)
    d["title"] = m.group(1).strip() if m else ""
    body = prefix.split("\n", 1)[1] if "\n" in prefix else prefix   # skip the [HUMAN GATE — ...] header
    for key in ("severity", "component", "owner"):
        m = re.search(rf"{key}=([\w\-]+)", body)
        d[key] = m.group(1) if m else None
    m = re.search(r"evidence: (.+)", prefix)
    d["evidence"] = m.group(1).strip() if m else ""
    m = re.search(r"confidence=([0-9.]+)", prefix)
    d["confidence"] = float(m.group(1)) if m else None
    return d


class _Slot:
    """A run's claim on the project: the per-project advisory lock (held on a
    dedicated connection) plus one worker slot. Parked at the human gate, both
    are given up so the next task can start; they are re-acquired on resume."""

    def __init__(self, conn: asyncpg.Connection, project_id: str, sem: asyncio.Semaphore) -> None:
        self.conn, self.key, self.sem = conn, f"project-run:{project_id}", sem
        self.held = True

    async def park(self) -> None:
        if not self.held:
            return
        self.held = False
        await self.conn.execute("SELECT pg_advisory_unlock(hashtext($1))", self.key)
        self.sem.release()

    async def resume(self) -> None:
        if self.held:
            return
        await self.sem.acquire()
        await self.conn.execute("SELECT pg_advisory_lock(hashtext($1))", self.key)   # blocks until the project is free
        self.held = True

    async def close(self) -> None:
        try:
            await self.conn.execute("SELECT pg_advisory_unlock_all()")
            await self.conn.close()
        except Exception:
            pass
        if self.held:
            self.held = False
            self.sem.release()


class RunService:
    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future] = {}      # approval id -> future (this replica)
        self._cancel: dict[str, asyncio.Event] = {}        # run id -> cancel flag (this replica)
        self._artifact_hooks: dict[str, Any] = {}          # run id -> per-run artifact handler
        self._parked: set[str] = set()                     # run ids waiting at the gate on this replica
        self._tasks: set[asyncio.Task] = set()
        self._slots: Optional[asyncio.Semaphore] = None
        self._stopping = False

    # ----------------------------------------------------------- API side --
    async def enqueue(self, session: AsyncSession, project: Project, task: Task, *, auto_approve: bool = False, preapproved: Optional[str] = None) -> Run:
        run = Run(id=new_run_id(), project_id=project.id, task_id=task.id, status="queued", auto_approve=auto_approve, preapproved=preapproved)
        session.add(run)
        task.status, task.last_run_id = "queued", run.id
        await session.flush()
        await activity.log(session, project, "RUN", f"queued {run.id} for {task.external_id}", ref_type="run", ref_id=run.id)
        await bus.publish_project(session, project.id, project.owner_id, "run.status", {"run_id": run.id, "status": "queued", "task_id": task.id})
        return run

    async def request_cancel(self, session: AsyncSession, project: Project, run: Run) -> bool:
        if run.status not in ACTIVE:
            return False
        if run.status == "queued":
            run.status, run.error, run.ended_at = "cancelled", "cancelled before start", now()
            task = await session.get(Task, run.task_id) if run.task_id else None
            if task:
                task.status = "failed"
            await bus.publish_project(session, project.id, project.owner_id, "run.status", {"run_id": run.id, "status": "cancelled", "task_id": run.task_id})
            return True
        run.cancel_requested = True
        await bus.publish(session, "system", "run.cancel", {"run_id": run.id})
        return True

    async def resolve_approval(self, session: AsyncSession, project: Project, appr: Approval, answer: str, status: str) -> None:
        appr.status, appr.resolved_at, appr.response = status, now(), {"answer": answer}
        await session.flush()
        run = await session.get(Run, appr.run_id)
        if run is not None and run.status != "waiting_approval":
            # The worker that held this run is gone (restart / crash). Re-run the task with
            # the decision carried over so the human is not asked twice.
            task = await session.get(Task, run.task_id) if run.task_id else None
            if task is not None and answer != "n":
                rerun = await self.enqueue(session, project, task, auto_approve=False, preapproved=answer)
                appr.response = {"answer": answer, "rerun_id": rerun.id}
                await activity.log(session, project, "RUN", f"{run.id} was interrupted; re-running {task.external_id} as {rerun.id} with your decision", ref_type="run", ref_id=rerun.id)
            elif task is not None:
                task.status = "done"
                task.result = {"outcome": "dropped", "feedback_id": task.external_id, "category": "bug"}
        await bus.publish(session, "system", "approval.answer", {"approval_id": appr.id, "answer": answer})
        await bus.publish_project(session, project.id, project.owner_id, "approval.resolved", {"id": appr.id, "run_id": appr.run_id, "status": status})
        await activity.log(session, project, "APPROVAL", f"{status} {appr.id}", ref_type="approval", ref_id=appr.id)

    # -------------------------------------------------------------- worker --
    async def start(self) -> None:
        self._stopping = False
        self._slots = asyncio.Semaphore(settings.RUN_WORKERS)
        bus.off(self._on_bus)
        bus.on(self._on_bus)
        for coro in (self._poll_loop(), self._sweep_loop()):
            t = asyncio.create_task(coro)
            self._tasks.add(t)
            t.add_done_callback(self._tasks.discard)

    async def stop(self) -> None:
        self._stopping = True
        bus.off(self._on_bus)
        if self._parked:
            async with SessionLocal() as s:
                await s.execute(update(Run).where(Run.id.in_(list(self._parked)), Run.status == "waiting_approval")
                                .values(status="error", error="interrupted while awaiting approval; your decision will re-run it", ended_at=now()))
                await s.commit()
        for t in list(self._tasks):
            t.cancel()
        try:
            await asyncio.wait_for(asyncio.gather(*list(self._tasks), return_exceptions=True), timeout=10)
        except (asyncio.TimeoutError, Exception):
            log.warning("run tasks did not finish within 10s; exiting anyway")
        self._tasks.clear()

    async def _on_bus(self, channel: str, type_: str, payload: dict) -> None:
        if type_ == "approval.answer":
            fut = self._pending.get(payload.get("approval_id", ""))
            if fut and not fut.done():
                fut.set_result(payload.get("answer", "n"))
        elif type_ == "run.cancel":
            ev = self._cancel.get(payload.get("run_id", ""))
            if ev:
                ev.set()
        elif type_ == "runtime.invalidate":
            runtimes.invalidate(payload.get("project_id", ""))

    def _dsn(self) -> str:
        return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    async def _poll_loop(self) -> None:
        while not self._stopping:
            try:
                await self._slots.acquire()
                claimed = await self._claim()
                if claimed is None:
                    self._slots.release()
                    await asyncio.sleep(settings.RUN_POLL_S)
                    continue
                run_id, conn, pid = claimed
                t = asyncio.create_task(self._run_guarded(run_id, _Slot(conn, pid, self._slots)))
                self._tasks.add(t)
                t.add_done_callback(self._tasks.discard)
            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("poll loop error")
                await asyncio.sleep(2)

    async def _claim(self) -> Optional[tuple[str, asyncpg.Connection, str]]:
        async with SessionLocal() as s:
            rows = (await s.execute(select(Run.id, Run.project_id).where(Run.status == "queued").order_by(Run.started_at).limit(25))).all()
        for rid, pid in rows:
            conn = await asyncpg.connect(self._dsn())
            try:
                if not await conn.fetchval("SELECT pg_try_advisory_lock(hashtext($1))", f"project-run:{pid}"):
                    await conn.close()
                    continue   # another replica is running this project
                got = await conn.fetchval(
                    "UPDATE runs SET status='running', worker_id=$1, heartbeat_at=now(), started_at=now() WHERE id=$2 AND status='queued' RETURNING id",
                    REPLICA_ID, rid,
                )
                if got:
                    return rid, conn, pid
                await conn.execute("SELECT pg_advisory_unlock(hashtext($1))", f"project-run:{pid}")
                await conn.close()
            except Exception:
                await conn.close()
                raise
        return None

    async def _run_guarded(self, run_id: str, slot: _Slot) -> None:
        self._cancel[run_id] = asyncio.Event()
        hb = asyncio.create_task(self._heartbeat(run_id))
        try:
            await self._execute(run_id, slot)
        except Exception:
            log.exception("run %s crashed", run_id)
            await self._mark_crashed(run_id)
        finally:
            hb.cancel()
            self._cancel.pop(run_id, None)
            await slot.close()

    async def _heartbeat(self, run_id: str) -> None:
        while True:
            await asyncio.sleep(settings.RUN_HEARTBEAT_S)
            try:
                async with SessionLocal() as s:
                    flag = (await s.execute(
                        update(Run).where(Run.id == run_id).values(heartbeat_at=now()).returning(Run.cancel_requested)
                    )).scalar()
                    await s.commit()
                if flag and run_id in self._cancel:
                    self._cancel[run_id].set()
            except asyncio.CancelledError:
                return
            except Exception:
                log.warning("heartbeat failed for %s", run_id)

    async def _mark_crashed(self, run_id: str) -> None:
        async with SessionLocal() as s:
            run = await s.get(Run, run_id)
            if run and run.status in ACTIVE:
                parked = run.status == "waiting_approval"
                run.status, run.error, run.ended_at = "error", "worker crashed", now()
                if run.task_id:
                    await s.execute(update(Task).where(Task.id == run.task_id).values(status="failed"))
                if not parked:
                    await s.execute(update(Approval).where(Approval.run_id == run_id, Approval.status == "pending").values(status="expired", resolved_at=now()))
                await s.execute(update(Agent).where(Agent.project_id == run.project_id).values(status="idle", current_process=None))
                p = await s.get(Project, run.project_id)
                await bus.publish_project(s, p.id, p.owner_id, "run.status", {"run_id": run.id, "status": "error", "task_id": run.task_id})
            await s.commit()

    async def _sweep_loop(self) -> None:
        """Any replica: runs whose worker stopped heartbeating are dead."""
        while not self._stopping:
            try:
                await asyncio.sleep(settings.RUN_STALE_S // 2)
                cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.RUN_STALE_S)
                async with SessionLocal() as s:
                    stale = (await s.execute(select(Run).where(Run.status.in_(("running", "waiting_approval")), Run.heartbeat_at < cutoff))).scalars().all()
                    for run in stale:
                        parked = run.status == "waiting_approval"
                        run.status, run.ended_at = "error", now()
                        run.error = "interrupted while awaiting approval; your decision will re-run it" if parked else "worker lost (no heartbeat)"
                        if run.task_id:
                            await s.execute(update(Task).where(Task.id == run.task_id).values(status="failed"))
                        if not parked:   # a pending approval outlives its worker; resolving it re-runs the task
                            await s.execute(update(Approval).where(Approval.run_id == run.id, Approval.status == "pending").values(status="expired", resolved_at=now()))
                        await s.execute(update(Agent).where(Agent.project_id == run.project_id).values(status="idle", current_process=None))
                        p = await s.get(Project, run.project_id)
                        await activity.log(s, p, "RUN", f"{run.id} failed: worker lost", ref_type="run", ref_id=run.id)
                        await bus.publish_project(s, p.id, p.owner_id, "run.status", {"run_id": run.id, "status": "error", "task_id": run.task_id})
                    await s.commit()
            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("sweep failed")

    # ------------------------------------------------------------- execute --
    async def _execute(self, run_id: str, slot: _Slot) -> None:
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            project = await session.get(Project, run.project_id)
            task = await session.get(Task, run.task_id)
            owner = await session.get(User, project.owner_id)
            us = await session.get(UserSettings, owner.id)
            cfg = ResolvedLlmConfig.from_settings(us)
            agents = (await session.execute(select(Agent).where(Agent.project_id == project.id).order_by(Agent.position))).scalars().all()
            agent_by_name = {a.name: a for a in agents}
            cancel = self._cancel[run_id]

            seq = {"n": 0}
            t_run = time.perf_counter()
            last_tool: dict[str, float] = {}
            visited: list[str] = []
            current = {"agent": None}

            async def pub(type_: str, payload: dict, headline: str | None = None) -> None:
                await bus.publish_project(session, project.id, project.owner_id, type_, payload, headline=headline)

            async def event(kind: str, actor: str, message: str, *, input=None, output=None, meta=None, duration_ms=None) -> None:
                seq["n"] += 1
                row = RunEvent(project_id=project.id, run_id=run.id, seq=seq["n"], kind=kind, actor=actor, message=message,
                               input=_jsonable(input), output=_jsonable(output), meta=meta or {}, duration_ms=duration_ms)
                session.add(row)
                await session.flush()
                await pub("run.event", {"run_id": run.id, "id": row.id, "seq": row.seq, "ts": row.ts, "kind": kind, "actor": actor, "message": message,
                                        "input": row.input, "output": row.output, "meta": row.meta, "duration_ms": duration_ms})

            async def set_agent(name: Optional[str], status: str, process: Optional[str] = None) -> None:
                a = agent_by_name.get(name or "")
                if a is None:
                    return
                a.status, a.current_process, a.last_active_at = status, process, now()
                await session.flush()
                await pub("agent.status", {"agent_id": a.id, "name": a.name, "status": status, "current_process": process, "last_active_at": a.last_active_at})

            async def set_run(status: str, **fields) -> None:
                run.status = status
                for k, v in fields.items():
                    setattr(run, k, v)
                await session.flush()
                await pub("run.status", {"run_id": run.id, "status": status, "current_agent": run.current_agent, "task_id": run.task_id}, headline=f"RUN {run.id} {status}")

            async def fail(msg: str) -> None:
                await event("ERROR", "SYSTEM", msg)
                await set_run("error", error=msg, ended_at=now(), duration_ms=int((time.perf_counter() - t_run) * 1000))
                task.status = "failed"
                for n in visited:
                    await set_agent(n, "error", None)
                await activity.log(session, project, "RUN", f"{run.id} failed: {msg[:120]}", ref_type="run", ref_id=run.id)
                await session.commit()
                integrations.notify(project.id, "run.failed", {"run_id": run.id, "error": msg, "task": task.external_id})

            # ---- preflight
            ok, why = cfg.ready()
            if not ok:
                await fail(why)
                return
            specs = [AgentSpec(name=a.name, description=a.description, instructions=a.instructions, tools=list(a.tools or []),
                               can_handoff_to=list(a.can_handoff_to or []), model=a.model, role=a.role, enabled=a.enabled) for a in agents]
            if not any(s.enabled for s in specs):
                await fail("This project has no enabled agents.")
                return

            run.starting_agent = next(s.name for s in specs if s.enabled)
            task.status = "running"
            await set_run("running")
            await event("SYSTEM", "SYSTEM", "Run initialized", meta={"task": task.external_id, "auto_approve": run.auto_approve, "worker": REPLICA_ID})
            await session.commit()

            try:
                rt = await runtimes.get_runtime(session, project, cfg)
            except Exception as exc:
                await fail(f"Could not prepare project runtime: {type(exc).__name__}: {exc}")
                return

            pcfg = project.config or {}
            pinned = (await session.execute(
                select(Memory).where(Memory.project_id == project.id, Memory.type == "PROJECT_CONTEXT", Memory.pinned.is_(True)).order_by(Memory.created_at)
            )).scalars().all() if pcfg.get("memory_pin_context", True) else []
            context = "\n".join([project.instructions.strip()] + [m.content for m in pinned]).strip()
            await event("MEMORY", "MEMORY", f"Project context retrieved ({len(pinned)} pinned memories)")

            factory = RunLlmFactory(cfg)
            try:
                workflow = build_workflow(specs, lambda spec: factory.for_agent(spec.name, spec.model), project_context=context)
            except Exception as exc:
                await fail(f"Could not build workflow: {exc}")
                return

            # ---- engine -> DB/bus bridge (single drain coroutine owns the session)
            queue: asyncio.Queue = asyncio.Queue()

            def on_event(kind: str, payload) -> None:
                queue.put_nowait((kind, payload))

            # The runtime is shared by every run of the project, so the hook must route by run id.
            self._artifact_hooks[run.id] = lambda sub, name, path: queue.put_nowait(("artifact", (sub, name, path)))
            rt.artifact_hook = self._dispatch_artifact

            async def handle_artifact(sub: str, name: str, path) -> None:
                rel = f"/out/{sub}/{name}.md"
                md = path.read_bytes()
                await storage.write_file(session, project, rel, md, "text/markdown")
                jpath = path.with_suffix(".json")
                if jpath.exists():
                    await storage.write_file(session, project, f"/out/{sub}/{name}.json", jpath.read_bytes(), "application/json")
                    if sub == "tickets":
                        integrations.notify(project.id, "ticket.created", {"ticket": json.loads(jpath.read_bytes()), "markdown": md.decode("utf-8", errors="replace"), "run_id": run.id})
                await activity.log(session, project, "FILE", f"written {rel}", ref_type="file", ref_id=rel)
                await event("SYSTEM", "WRITER", f"artifact {rel}", meta={"kind": sub})

            async def handle_gate(prompt: str) -> str:
                info = _parse_gate(prompt)
                aid = approval_id()
                appr = Approval(id=aid, project_id=project.id, run_id=run.id, agent_name=current["agent"] or "",
                                action=f"Create {info.get('severity') or ''} severity ticket: {info.get('title') or ''}".strip(),
                                reason=info.get("reason_raw") or "gate threshold", confidence=info.get("confidence"), details=info, status="pending")
                session.add(appr)
                run.approval_state = "pending"
                await set_run("waiting_approval")
                await set_agent(current["agent"], "human_input", "awaiting human approval")
                await event("APPROVAL", "SYSTEM", f"approval requested {aid}: {appr.action}", meta={"approval_id": aid})
                await activity.log(session, project, "APPROVAL", f"requested {aid} ({appr.action[:80]})", ref_type="approval", ref_id=aid)
                await pub("approval.requested", {"id": aid, "run_id": run.id, "agent_name": appr.agent_name, "action": appr.action, "reason": appr.reason,
                                                 "confidence": appr.confidence, "details": info, "requested_at": appr.requested_at}, headline=f"APPROVAL requested {aid}")
                await session.commit()
                integrations.notify(project.id, "approval.requested", {"id": aid, "run_id": run.id, "agent_name": appr.agent_name, "action": appr.action, "reason": appr.reason, "confidence": appr.confidence})

                # Free the project for the next task while a human decides.
                await slot.park()
                self._parked.add(run.id)
                fut: asyncio.Future = asyncio.get_running_loop().create_future()
                self._pending[aid] = fut
                cancel_wait = asyncio.ensure_future(cancel.wait())
                try:
                    # Wait for the bus; poll the row as a fallback in case the NOTIFY was missed.
                    while not fut.done():
                        await asyncio.wait({fut, cancel_wait}, timeout=5, return_when=asyncio.FIRST_COMPLETED)
                        if cancel.is_set() and not fut.done():
                            fut.set_result("n")
                        if not fut.done():
                            async with SessionLocal() as s2:
                                a2 = await s2.get(Approval, aid)
                                if a2 and a2.status != "pending":
                                    fut.set_result((a2.response or {}).get("answer", "n"))
                    answer = fut.result()
                finally:
                    self._pending.pop(aid, None)
                    cancel_wait.cancel()
                self._parked.discard(run.id)
                await slot.resume()   # waits if another run in this project is mid-flight
                await session.refresh(appr)
                status = {"y": "approved", "n": "rejected"}.get(answer, "modified")
                if appr.status == "pending":   # resolved via cancel, not the API
                    appr.status, appr.resolved_at, appr.response = status, now(), {"answer": answer}
                run.approval_state = appr.status
                await set_run("running")
                await set_agent(current["agent"], "running", "resuming after approval")
                await event("APPROVAL", "HUMAN", appr.status + (f" (severity → {answer})" if status == "modified" else ""), meta={"approval_id": aid})
                await session.commit()
                return answer

            async def ask_human(prompt: str) -> str:
                done: asyncio.Future = asyncio.get_running_loop().create_future()
                queue.put_nowait(("gate", (prompt, done)))
                return await done

            async def handle(kind: str, payload) -> None:
                if kind == "artifact":
                    await handle_artifact(*payload)
                elif kind == "gate":
                    prompt, done = payload
                    try:
                        done.set_result(await handle_gate(prompt))
                    except Exception as exc:
                        done.set_exception(exc)
                elif kind == "agent":
                    if current["agent"]:
                        await set_agent(current["agent"], "complete", None)
                    current["agent"] = payload
                    visited.append(payload)
                    run.current_agent = payload
                    await set_agent(payload, "thinking", "task received")
                    await event("AGENT", payload.upper(), "Task received" if len(visited) == 1 else "Took over after handoff")
                    await pub("run.status", {"run_id": run.id, "status": run.status, "current_agent": payload, "task_id": run.task_id})
                elif kind == "handoff":
                    frm, to = payload
                    run.handoff_count += 1
                    await event("HANDOFF", frm.upper(), f"{frm} → {to}", meta={"from": frm, "to": to})
                    await pub("agent.handoff", {"run_id": run.id, "from": frm, "to": to})
                elif kind == "tool_call":
                    run.tool_call_count += 1
                    last_tool[payload.tool_id] = time.perf_counter()
                    args = {k: _jsonable(v) for k, v in (payload.tool_kwargs or {}).items()}
                    await set_agent(current["agent"], "tool_call", f"{payload.tool_name}()")
                    await event("TOOL", (current["agent"] or "tool").upper(), f"{payload.tool_name}()", input=args, meta={"tool_id": payload.tool_id})
                elif kind == "tool_result":
                    t0 = last_tool.pop(payload.tool_id, None)
                    dur = int((time.perf_counter() - t0) * 1000) if t0 else None
                    out = str(payload.tool_output)
                    is_err = bool(getattr(payload.tool_output, "is_error", False))
                    session.add(ToolCallRow(project_id=project.id, run_id=run.id, agent_name=current["agent"] or "", tool_name=payload.tool_name,
                                            args={k: _jsonable(v) for k, v in (payload.tool_kwargs or {}).items()}, result=out[:20000], is_error=is_err, duration_ms=dur))
                    await set_agent(current["agent"], "thinking", f"processing {payload.tool_name} result")
                    await event("TOOL_RESULT", payload.tool_name.upper(), (out.splitlines()[0][:160] if out else ""), output={"text": out[:20000]},
                                meta={"tool_id": payload.tool_id, "is_error": is_err}, duration_ms=dur)
                    if payload.tool_name in ("search_recent_reports", "search_knowledge"):
                        await event("MEMORY", "MEMORY", f"{payload.tool_name}: {out.splitlines()[0][:120] if out else ''}")
                elif kind == "agent_output":
                    if not getattr(payload, "tool_calls", None):
                        text_ = str(getattr(payload.response, "content", "") or "").strip()
                        if text_:
                            await event("AGENT", (current["agent"] or "agent").upper(), text_[:300], output={"text": text_[:4000]})
                elif kind == "final":
                    await event("FINAL", "SYSTEM", (payload or "")[:300])
                elif kind == "error":
                    await event("ERROR", "SYSTEM", str(payload)[:500])
                await session.commit()

            async def drain() -> None:
                while True:
                    item = await queue.get()
                    if item is None:
                        return
                    try:
                        await handle(*item)
                    except Exception:
                        log.exception("event handling failed")

            fb = RawFeedback(id=task.external_id, source=task.source, received_at=task.received_at or run.started_at.isoformat(),
                             author=task.author or "unknown", rating=task.rating, metadata=task.meta or {}, text=task.text)
            sev_floor = {"critical": ["critical"], "high": ["high", "critical"], "medium": ["medium", "high", "critical"]}.get(str(pcfg.get("gate_severity", "high")), ["high", "critical"])
            gate = {"severities": sev_floor, "min_confidence": float(pcfg.get("gate_min_confidence", 0.7))}
            extra = {"gate": gate, "run_id": run.id}
            if run.preapproved:
                extra["preapproved"] = run.preapproved
                await event("APPROVAL", "HUMAN", f"decision carried over from the interrupted attempt: {run.preapproved}")
            runner = Runner(workflow, rt, auto_approve=run.auto_approve, on_event=on_event, ask_human=ask_human, extra_state=extra)
            drainer = asyncio.create_task(drain())
            try:
                result, rlog = await runner.run_one(fb, cancel=cancel)
            finally:
                queue.put_nowait(None)
                await drainer
                self._artifact_hooks.pop(run.id, None)

            # ---- wrap up
            dur = int((time.perf_counter() - t_run) * 1000)
            for n in visited:
                await set_agent(n, "idle", None)
            run.result = result.model_dump()
            run.final_text = rlog.final_text
            if run.preapproved and result.outcome == "new_ticket":
                run.approval_state = "approved" if run.preapproved == "y" else "modified"
            task.result = result.model_dump()
            if cancel.is_set():
                await set_run("cancelled", ended_at=now(), duration_ms=dur, error="cancelled by user")
                task.status = "failed"
                await activity.log(session, project, "RUN", f"{run.id} cancelled", ref_type="run", ref_id=run.id)
            elif rlog.error:
                await set_run("error", ended_at=now(), duration_ms=dur, error=rlog.error)
                task.status = "failed"
                await activity.log(session, project, "RUN", f"{run.id} failed: {rlog.error[:120]}", ref_type="run", ref_id=run.id)
                integrations.notify(project.id, "run.failed", {"run_id": run.id, "error": rlog.error, "task": task.external_id})
            else:
                await set_run("complete", ended_at=now(), duration_ms=dur)
                task.status = "done"
                ref = result.ticket_id or result.duplicate_of or ""
                await activity.log(session, project, "RUN", f"{run.id} complete: {result.outcome} {ref}".strip(), ref_type="run", ref_id=run.id)
                if pcfg.get("memory_auto_write", True):
                    await self._write_memories(session, project, run, task, result)
            try:
                await usage.record_run_usage(session, project, run, factory)
            except Exception:
                log.exception("usage accounting failed")
            await session.commit()

    def _dispatch_artifact(self, sub: str, name: str, path, payload: dict, run_id: Optional[str]) -> None:
        hook = self._artifact_hooks.get(run_id or "")
        if hook is not None:
            hook(sub, name, path)
        else:
            log.warning("artifact %s/%s written by unknown run %s", sub, name, run_id)

    async def _write_memories(self, session: AsyncSession, project: Project, run: Run, task: Task, result) -> None:
        ref = result.ticket_id or result.duplicate_of

        def add(type_: str, source: str, content: str) -> None:
            session.add(Memory(id=memory_id(), project_id=project.id, type=type_, source=source, content=content, related_run_id=run.id))

        summary = f"{task.external_id}: {result.outcome}" + (f" → {ref}" if ref else "") + (f" [{result.severity}/{result.component}]" if result.severity else "")
        add("COMPLETED_WORK", "system", summary)
        if result.outcome == "new_ticket" and ref:
            add("DECISIONS", "agent_writer", f"Created {ref} ({result.severity}, {result.component}) for {task.external_id}." + (" Approved by a human reviewer." if run.approval_state in ("approved", "modified") else ""))
        if result.outcome == "duplicate" and ref:
            add("AGENT_NOTES", "agent_investigator", f"{task.external_id} is a duplicate of {ref}.")
        if result.outcome == "needs_info":
            add("AGENT_NOTES", "agent_investigator", f"{task.external_id} lacked actionable detail; clarification requested.")
        if run.approval_state == "modified":
            add("DECISIONS", "human", f"Reviewer overrode the proposed severity on {run.id} to {result.severity}.")
        await session.flush()
        await activity.log(session, project, "MEMORY", f"updated ({result.outcome})", ref_type="run", ref_id=run.id)
        await bus.publish_project(session, project.id, project.owner_id, "memory.updated", {"run_id": run.id})


run_service = RunService()
