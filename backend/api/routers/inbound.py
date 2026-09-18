"""Inbound integration endpoints.

    POST /api/inbound/{provider}/{project_id}[?token=…]   called by Slack / GitHub / Jira / … (no user session)
    POST /api/projects/{id}/integrations/{provider}/sync  SYNC NOW for pull providers (owner)
    POST /api/projects/{id}/integrations/{provider}/inbound-token   rotate the URL token (owner)
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from ..core.deps import ProjectDep, Session
from ..integrations import inbound as inbound_svc
from ..integrations.adapters import _plain
from ..integrations.catalog import CATALOG
from ..models import Integration, Project
from ..services import activity
from ..services import tasks as task_service
from ..services.sync import sync_scheduler

router = APIRouter(tags=["inbound"])


async def _row(session, project_id: str, provider: str) -> Integration | None:
    return (await session.execute(select(Integration).where(Integration.project_id == project_id, Integration.provider == provider))).scalar_one_or_none()


@router.post("/api/inbound/{provider}/{project_id}")
async def inbound(provider: str, project_id: str, request: Request, session: Session):
    if provider not in CATALOG:
        raise HTTPException(404, "unknown provider")
    project = await session.get(Project, project_id)
    row = await _row(session, project_id, provider) if project else None
    if project is None or row is None or row.status not in ("connected", "error"):
        raise HTTPException(401, "integration not connected")
    body = await request.body()
    token_ok = bool(row.inbound_token) and secrets.compare_digest(request.query_params.get("token", ""), row.inbound_token)
    items, response = await inbound_svc.handle(provider, request, body, _plain(row.config or {}), token_ok)
    if provider == "slack" and isinstance(response, dict) and "challenge" in response:
        row.config = {**(row.config or {}), "_inbound_verified": True}
        await session.commit()
        return response
    if items:
        res = await task_service.ingest(session, project, items, source=provider, log_as=provider.upper())
        row.inbound_count = (row.inbound_count or 0) + len(res["created"])
        if row.status == "error":
            row.status = "connected"
        await session.commit()
        return {**res, **(response if isinstance(response, dict) else {})}
    await session.commit()
    return response


@router.post("/api/projects/{project_id}/integrations/{provider}/sync")
async def sync_now(provider: str, project: ProjectDep, session: Session):
    row = await _row(session, project.id, provider)
    if row is None or row.status == "not_connected":
        raise HTTPException(409, "connect the integration first")
    if CATALOG[provider]["inbound"]["mode"] == "push":
        raise HTTPException(409, "this provider pushes to the inbound URL; nothing to poll")
    result = await sync_scheduler.run_sync(row.id, manual=True)
    return {"result": result}


@router.post("/api/projects/{project_id}/integrations/{provider}/inbound-token")
async def rotate_inbound_token(provider: str, project: ProjectDep, session: Session):
    if provider not in CATALOG:
        raise HTTPException(404, "unknown provider")
    row = await _row(session, project.id, provider)
    if row is None:
        row = Integration(project_id=project.id, provider=provider)
        session.add(row)
    row.inbound_token = secrets.token_urlsafe(24)
    await activity.log(session, project, "SYSTEM", f"{provider} inbound token rotated", ref_type="integration", ref_id=provider)
    await session.commit()
    return {"token": row.inbound_token}
