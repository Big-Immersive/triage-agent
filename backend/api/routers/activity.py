from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from ..core.deps import CurrentUser, ProjectDep, Session
from ..models import Activity, Project
from ..schemas import ActivityOut

router = APIRouter(tags=["activity"])
CATS = ("AGENT", "RUN", "MEMORY", "FILE", "KNOWLEDGE", "APPROVAL", "SYSTEM", "PROJECT")


@router.get("/api/projects/{project_id}/activity", response_model=list[ActivityOut])
async def project_activity(project: ProjectDep, session: Session, category: str | None = None, limit: int = 200, before_id: int | None = None):
    q = select(Activity).where(Activity.project_id == project.id)
    if category and category != "ALL":
        cats = ("AGENT",) if category == "AGENTS" else ("RUN",) if category == "RUNS" else ("FILE",) if category == "FILES" else ("APPROVAL",) if category == "APPROVALS" else ("SYSTEM", "PROJECT", "KNOWLEDGE") if category == "SYSTEM" else (category,)
        q = q.where(Activity.category.in_(cats))
    if before_id:
        q = q.where(Activity.id < before_id)
    return (await session.execute(q.order_by(Activity.id.desc()).limit(min(limit, 500)))).scalars().all()


@router.get("/api/activity")
async def global_activity(user: CurrentUser, session: Session, limit: int = 100):
    """Headlines across the user's projects — never memory or knowledge content."""
    rows = (await session.execute(
        select(Activity, Project.name, Project.slug).join(Project, Project.id == Activity.project_id)
        .where(Project.owner_id == user.id).order_by(Activity.id.desc()).limit(min(limit, 500))
    )).all()
    return [{"id": a.id, "ts": a.ts, "category": a.category, "message": a.message, "project_id": a.project_id, "project_name": name, "project_slug": slug, "ref_type": a.ref_type, "ref_id": a.ref_id} for a, name, slug in rows]
