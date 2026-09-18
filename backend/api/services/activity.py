"""Activity log + project timestamp + bus broadcast in one call."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.bus import bus
from ..models import Activity, Project, now


async def log(
    session: AsyncSession,
    project: Project,
    category: str,
    message: str,
    *,
    ref_type: str | None = None,
    ref_id: str | None = None,
    publish: bool = True,
) -> Activity:
    row = Activity(project_id=project.id, category=category, message=message, ref_type=ref_type, ref_id=ref_id)
    session.add(row)
    project.last_activity_at = now()
    await session.flush()
    if publish:
        await bus.publish_project(
            session, project.id, project.owner_id, "activity",
            {"id": row.id, "ts": row.ts, "category": category, "message": message, "ref_type": ref_type, "ref_id": ref_id},
            headline=f"{category} {message}",
        )
    return row
