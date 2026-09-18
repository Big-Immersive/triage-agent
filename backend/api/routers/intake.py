"""Inbound intake: external systems push feedback into a project with a per-project key.

    POST /api/intake/{project_id}
    X-Intake-Key: <key>
    {"items": [{"id": "...", "source": "app_store", "author": "...", "text": "...", "rating": 1, "metadata": {"app_version": "2.4.1"}}]}

A single item object is accepted too. Tasks are created and, when the project
has auto_run on (default), executed immediately. The key is stored hashed; it
is shown once when generated under settings > security.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..core.deps import ProjectDep, Session
from ..models import Project, Task
from ..services import activity
from ..services import tasks as task_service

router = APIRouter(tags=["intake"])


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@router.post("/api/projects/{project_id}/intake-key")
async def rotate_key(project: ProjectDep, session: Session):
    """Generate (or rotate) the project's intake key. Returned once, stored as a hash."""
    key = "tik_" + secrets.token_urlsafe(24)
    project.config = {**(project.config or {}), "intake_key_hash": _hash(key), "intake_key_hint": key[:8] + "…"}
    await activity.log(session, project, "SYSTEM", "intake key rotated", ref_type="project", ref_id=project.id)
    await session.commit()
    return {"key": key, "hint": project.config["intake_key_hint"], "endpoint": f"/api/intake/{project.id}"}


@router.delete("/api/projects/{project_id}/intake-key", status_code=204)
async def revoke_key(project: ProjectDep, session: Session):
    cfg = dict(project.config or {})
    cfg.pop("intake_key_hash", None); cfg.pop("intake_key_hint", None)
    project.config = cfg
    await activity.log(session, project, "SYSTEM", "intake key revoked", ref_type="project", ref_id=project.id)
    await session.commit()


class IntakeIn(BaseModel):
    items: list[dict[str, Any]] | None = None
    # single-item shape
    id: str | None = None
    source: str | None = None
    author: str | None = None
    text: str | None = None
    rating: int | None = None
    received_at: str | None = None
    metadata: dict[str, Any] | None = None


@router.post("/api/intake/{project_id}")
async def intake(project_id: str, body: IntakeIn, session: Session, x_intake_key: str = Header(default="")):
    project = await session.get(Project, project_id)
    stored = (project.config or {}).get("intake_key_hash") if project else None
    if project is None or not stored or not x_intake_key or _hash(x_intake_key) != stored:
        raise HTTPException(401, "invalid intake key")
    items = body.items if body.items is not None else [body.model_dump(exclude={"items"}, exclude_none=True)]
    result = await task_service.ingest(session, project, items, source="intake", log_as="intake")
    await session.commit()
    return result
