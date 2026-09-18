"""Turning external items into tasks (and runs). Shared by the tasks router,
the intake endpoint and every inbound integration."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Project, Task
from . import activity
from .runs import run_service


def default_auto_approve(project: Project) -> bool:
    return bool((project.config or {}).get("default_auto_approve", False))


async def next_external_id(session: AsyncSession, project_id: str) -> str:
    n = len((await session.execute(select(Task.id).where(Task.project_id == project_id))).all()) + 1
    while (await session.execute(select(Task.id).where(Task.project_id == project_id, Task.external_id == f"FB-{n:03d}"))).first():
        n += 1
    return f"FB-{n:03d}"


async def maybe_auto_run(session: AsyncSession, project: Project, tasks: list[Task]) -> list[str]:
    """Projects with auto_run (default on) start a run for every new task immediately."""
    if not (project.config or {}).get("auto_run", True):
        return []
    return [(await run_service.enqueue(session, project, t, auto_approve=default_auto_approve(project))).id for t in tasks]


async def ingest(session: AsyncSession, project: Project, items: list[dict[str, Any]], *, source: str, log_as: str) -> dict:
    """Create tasks from normalized items ({id?, source?, author?, text, rating?, received_at?, metadata?}),
    skipping empties and ids the project already has, then auto-run. Returns counts + ids."""
    existing = {t.external_id for t in (await session.execute(select(Task).where(Task.project_id == project.id))).scalars()}
    created: list[Task] = []
    skipped = 0
    for it in items[:500]:
        text = str(it.get("text") or "").strip()
        if not text:
            skipped += 1
            continue
        ext = str(it.get("id") or "").strip().upper() or await next_external_id(session, project.id)
        if ext in existing:
            skipped += 1
            continue
        existing.add(ext)
        t = Task(project_id=project.id, external_id=ext, source=str(it.get("source") or source), author=str(it.get("author") or ""),
                 title=text[:80].replace("\n", " "), text=text, rating=it.get("rating"), received_at=it.get("received_at"), meta=it.get("metadata") or {})
        session.add(t)
        created.append(t)
    await session.flush()
    if created:
        await activity.log(session, project, "SYSTEM", f"{log_as} received {len(created)} item(s)", ref_type="project", ref_id=project.id)
    queued = await maybe_auto_run(session, project, created)
    return {"created": [t.external_id for t in created], "skipped": skipped, "queued": queued}
