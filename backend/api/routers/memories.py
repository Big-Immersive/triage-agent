from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import or_, select

from ..core.bus import bus
from ..core.deps import ProjectDep, Session
from ..core.ids import memory_id
from ..models import Memory
from ..schemas import MemoryIn, MemoryOut, MemoryPatch
from ..services import activity

router = APIRouter(prefix="/api/projects/{project_id}/memories", tags=["memory"])


@router.get("", response_model=list[MemoryOut])
async def list_memories(project: ProjectDep, session: Session, type: str | None = None, q: str | None = None, limit: int = 200):
    stmt = select(Memory).where(Memory.project_id == project.id)
    if type and type != "ALL":
        stmt = stmt.where(Memory.type == type)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Memory.content.ilike(like), Memory.source.ilike(like), Memory.id.ilike(like), Memory.related_run_id.ilike(like)))
    return (await session.execute(stmt.order_by(Memory.pinned.desc(), Memory.created_at.desc()).limit(min(limit, 1000)))).scalars().all()


@router.post("", response_model=MemoryOut, status_code=201)
async def add_memory(body: MemoryIn, project: ProjectDep, session: Session):
    m = Memory(id=memory_id(), project_id=project.id, **body.model_dump())
    session.add(m)
    await session.flush()
    await activity.log(session, project, "MEMORY", f"added {m.id} ({m.type})", ref_type="memory", ref_id=m.id)
    await bus.publish_project(session, project.id, project.owner_id, "memory.updated", {"id": m.id})
    await session.commit()
    return m


async def _get(session, project, mid: str) -> Memory:
    m = await session.get(Memory, mid)
    if m is None or m.project_id != project.id:
        raise HTTPException(404, "Memory not found")
    return m


@router.patch("/{mid}", response_model=MemoryOut)
async def edit_memory(mid: str, body: MemoryPatch, project: ProjectDep, session: Session):
    m = await _get(session, project, mid)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(m, k, v)
    await activity.log(session, project, "MEMORY", f"edited {m.id}", ref_type="memory", ref_id=m.id)
    await bus.publish_project(session, project.id, project.owner_id, "memory.updated", {"id": m.id})
    await session.commit()
    return m


@router.post("/{mid}/pin", response_model=MemoryOut)
async def pin_memory(mid: str, project: ProjectDep, session: Session):
    m = await _get(session, project, mid)
    m.pinned = not m.pinned
    await bus.publish_project(session, project.id, project.owner_id, "memory.updated", {"id": m.id})
    await session.commit()
    return m


@router.delete("/{mid}", status_code=204)
async def delete_memory(mid: str, project: ProjectDep, session: Session):
    m = await _get(session, project, mid)
    await activity.log(session, project, "MEMORY", f"deleted {m.id}", ref_type="memory", ref_id=m.id)
    await session.delete(m)
    await bus.publish_project(session, project.id, project.owner_id, "memory.updated", {"id": mid})
    await session.commit()
