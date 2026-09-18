from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, HTTPException, UploadFile
from sqlalchemy import select

from ..core.deps import ProjectDep, Session
from ..core.ids import task_id
from ..models import Run, Task
from ..schemas import TaskIn, TaskOut
from ..services import activity
from ..services import tasks as task_service
from ..services.runs import run_service

router = APIRouter(prefix="/api/projects/{project_id}/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
async def list_tasks(project: ProjectDep, session: Session, status: str | None = None):
    q = select(Task, Run.status).outerjoin(Run, Run.id == Task.last_run_id).where(Task.project_id == project.id)
    if status:
        q = q.where(Task.status == status)
    out = []
    for t, rs in (await session.execute(q.order_by(Task.created_at.desc()))).all():
        o = TaskOut.model_validate(t)
        o.last_run_status = rs
        out.append(o)
    return out


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(body: TaskIn, project: ProjectDep, session: Session):
    ext = (body.external_id or "").strip().upper() or await _next_ext(session, project.id)
    if (await session.execute(select(Task.id).where(Task.project_id == project.id, Task.external_id == ext))).first():
        raise HTTPException(409, f"Task {ext} already exists")
    t = Task(project_id=project.id, external_id=ext, source=body.source, author=body.author, title=body.title or body.text[:80].replace("\n", " "),
             text=body.text, rating=body.rating, received_at=body.received_at, meta=body.meta)
    session.add(t)
    await session.flush()
    await activity.log(session, project, "SYSTEM", f"task {ext} created", ref_type="task", ref_id=t.id)
    await maybe_auto_run(session, project, [t])
    await session.commit()
    return t


@router.post("/import")
async def import_tasks(project: ProjectDep, session: Session, file: UploadFile):
    """Upload the user's own feedback: a JSON array (inbox item shape) or a CSV with at least a `text` column."""
    raw = await file.read()
    name = (file.filename or "").lower()
    items: list[dict] = []
    try:
        if name.endswith(".json") or raw.lstrip().startswith(b"["):
            data = json.loads(raw.decode("utf-8"))
            items = data if isinstance(data, list) else data.get("items", [])
        else:
            for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
                meta = {k: v for k, v in row.items() if k in ("device", "os", "app_version") and v}
                items.append({"id": row.get("id"), "source": row.get("source", "import"), "author": row.get("author", ""), "text": row.get("text", ""),
                              "rating": int(row["rating"]) if row.get("rating") else None, "received_at": row.get("received_at"), "metadata": meta})
    except Exception as exc:
        raise HTTPException(422, f"Could not parse file: {exc}")
    existing = {t.external_id for t in (await session.execute(select(Task).where(Task.project_id == project.id))).scalars()}
    created, skipped = 0, 0
    new_tasks: list[Task] = []
    for it in items:
        text = (it.get("text") or "").strip()
        if not text:
            skipped += 1
            continue
        ext = (it.get("id") or "").strip().upper() or await _next_ext(session, project.id)
        if ext in existing:
            skipped += 1
            continue
        existing.add(ext)
        t = Task(project_id=project.id, external_id=ext, source=it.get("source") or "import", author=it.get("author") or "", title=text[:80].replace("\n", " "),
                 text=text, rating=it.get("rating"), received_at=it.get("received_at"), meta=it.get("metadata") or {})
        session.add(t)
        new_tasks.append(t)
        created += 1
    await session.flush()
    await activity.log(session, project, "SYSTEM", f"imported {created} tasks from {file.filename}", ref_type="project", ref_id=project.id)
    queued = await maybe_auto_run(session, project, new_tasks)
    await session.commit()
    return {"created": created, "skipped": skipped, "queued": len(queued)}


def _auto(project, auto_approve: bool | None) -> bool:
    return task_service.default_auto_approve(project) if auto_approve is None else auto_approve


maybe_auto_run = task_service.maybe_auto_run
_next_ext = task_service.next_external_id


@router.post("/{tid}/run")
async def run_task(tid: str, project: ProjectDep, session: Session, auto_approve: bool | None = None):
    auto_approve = _auto(project, auto_approve)
    t = await session.get(Task, tid)
    if t is None or t.project_id != project.id:
        raise HTTPException(404, "Task not found")
    if t.status in ("queued", "running") and (await session.execute(select(Run.id).where(Run.task_id == t.id, Run.status.in_(("queued", "running", "waiting_approval"))))).first():
        raise HTTPException(409, "Task already has an active run")
    run = await run_service.enqueue(session, project, t, auto_approve=auto_approve)
    await session.commit()
    return {"run_id": run.id, "status": run.status}


@router.post("/run-all")
async def run_all(project: ProjectDep, session: Session, auto_approve: bool | None = None, only_queued: bool = True):
    auto_approve = _auto(project, auto_approve)
    q = select(Task).where(Task.project_id == project.id)
    if only_queued:
        q = q.where(Task.status.in_(("queued", "failed")))
    tasks = (await session.execute(q.order_by(Task.external_id))).scalars().all()
    active = {r for r in (await session.execute(select(Run.task_id).where(Run.project_id == project.id, Run.status.in_(("queued", "running", "waiting_approval"))))).scalars()}
    ids = []
    for t in tasks:
        if t.id in active:
            continue
        ids.append((await run_service.enqueue(session, project, t, auto_approve=auto_approve)).id)
    await session.commit()
    return {"queued": len(ids), "run_ids": ids}


@router.delete("/{tid}", status_code=204)
async def delete_task(tid: str, project: ProjectDep, session: Session):
    t = await session.get(Task, tid)
    if t is None or t.project_id != project.id:
        raise HTTPException(404, "Task not found")
    await session.delete(t)
    await session.commit()
