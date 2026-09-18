"""Writer outputs: tickets, +1 comments, clarification replies and dropped items.
They are the /out artifacts the writer agent produced, read back from storage."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..core.deps import ProjectDep, Session
from ..models import File, Run
from ..services import storage

router = APIRouter(prefix="/api/projects/{project_id}/outputs", tags=["outputs"])
KINDS = {"tickets": "/out/tickets/", "comments": "/out/comments/", "replies": "/out/replies/", "dropped": "/out/dropped/"}


async def _load(session, project, kind: str) -> list[dict]:
    prefix = KINDS[kind]
    rows = (await session.execute(select(File).where(File.project_id == project.id, File.path.like(prefix + "%.json")).order_by(File.updated_at.desc()))).scalars().all()
    out = []
    for f in rows:
        try:
            data = json.loads((await storage.read_bytes(f)).decode("utf-8"))
        except Exception:
            continue
        out.append({**data, "_file_id": f.id, "_md_path": f.path[:-5] + ".md", "_created_at": f.created_at, "_updated_at": f.updated_at})
    return out


@router.get("")
async def list_outputs(project: ProjectDep, session: Session, kind: str = "tickets"):
    if kind not in KINDS:
        raise HTTPException(422, "kind must be tickets|comments|replies|dropped")
    items = await _load(session, project, kind)
    if kind == "tickets":
        # Which run created each ticket (for the link back to its console).
        runs = (await session.execute(select(Run.id, Run.result, Run.approval_state).where(Run.project_id == project.id, Run.status == "complete"))).all()
        by_ticket = {r.result.get("ticket_id"): (r.id, r.approval_state) for r in runs if r.result and r.result.get("ticket_id")}
        for t in items:
            rid, ap = by_ticket.get(t.get("id"), (None, None))
            t["run_id"], t["approval_state"] = rid, ap
    return items


@router.get("/counts")
async def counts(project: ProjectDep, session: Session):
    out = {}
    for kind, prefix in KINDS.items():
        out[kind] = len((await session.execute(select(File.id).where(File.project_id == project.id, File.path.like(prefix + "%.json")))).all())
    return out


@router.get("/{kind}/{name}")
async def get_output(kind: str, name: str, project: ProjectDep, session: Session):
    if kind not in KINDS:
        raise HTTPException(422, "bad kind")
    base = KINDS[kind] + name
    js = (await session.execute(select(File).where(File.project_id == project.id, File.path == base + ".json"))).scalar_one_or_none()
    md = (await session.execute(select(File).where(File.project_id == project.id, File.path == base + ".md"))).scalar_one_or_none()
    if js is None:
        raise HTTPException(404, "not found")
    return {"data": json.loads((await storage.read_bytes(js)).decode("utf-8")), "markdown": (await storage.read_bytes(md)).decode("utf-8", errors="replace") if md else "", "file_id": js.id, "md_file_id": md.id if md else None}
