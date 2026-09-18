from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..core.deps import ProjectDep, Session
from ..models import Run, RunEvent, Task, ToolCallRow
from ..schemas import RunEventOut, RunOut, ToolCallOut
from ..services.runs import run_service

router = APIRouter(prefix="/api/projects/{project_id}/runs", tags=["runs"])


def _out(run: Run, ext: str | None) -> RunOut:
    o = RunOut.model_validate(run)
    o.task_external_id = ext
    return o


@router.get("", response_model=list[RunOut])
async def list_runs(project: ProjectDep, session: Session, status: str | None = None, limit: int = 100):
    q = select(Run, Task.external_id).outerjoin(Task, Task.id == Run.task_id).where(Run.project_id == project.id)
    if status:
        q = q.where(Run.status == status)
    rows = (await session.execute(q.order_by(Run.started_at.desc()).limit(min(limit, 500)))).all()
    return [_out(r, ext) for r, ext in rows]


async def _get(session, project, run_id: str) -> tuple[Run, str | None]:
    row = (await session.execute(select(Run, Task.external_id).outerjoin(Task, Task.id == Run.task_id).where(Run.id == run_id, Run.project_id == project.id))).first()
    if row is None:
        raise HTTPException(404, "Run not found")
    return row[0], row[1]


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: str, project: ProjectDep, session: Session):
    run, ext = await _get(session, project, run_id)
    return _out(run, ext)


@router.get("/{run_id}/events", response_model=list[RunEventOut])
async def run_events(run_id: str, project: ProjectDep, session: Session, after_seq: int = 0):
    await _get(session, project, run_id)
    return (await session.execute(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq > after_seq).order_by(RunEvent.seq))).scalars().all()


@router.get("/{run_id}/tool-calls", response_model=list[ToolCallOut])
async def run_tool_calls(run_id: str, project: ProjectDep, session: Session):
    await _get(session, project, run_id)
    return (await session.execute(select(ToolCallRow).where(ToolCallRow.run_id == run_id).order_by(ToolCallRow.ts))).scalars().all()


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, project: ProjectDep, session: Session):
    run, _ = await _get(session, project, run_id)
    ok = await run_service.request_cancel(session, project, run)
    await session.commit()
    if not ok:
        raise HTTPException(409, "Run is not active")
    return {"ok": True, "status": run.status}
