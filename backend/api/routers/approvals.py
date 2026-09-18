from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..core.deps import ProjectDep, Session
from ..models import Approval
from ..schemas import ApprovalModifyIn, ApprovalOut
from ..services.runs import run_service

router = APIRouter(prefix="/api/projects/{project_id}/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(project: ProjectDep, session: Session, status: str | None = None):
    from ..models import Run
    q = select(Approval, Run.result).outerjoin(Run, Run.id == Approval.run_id).where(Approval.project_id == project.id)
    if status:
        q = q.where(Approval.status == status)
    out = []
    for a, result in (await session.execute(q.order_by(Approval.requested_at.desc()).limit(200))).all():
        o = ApprovalOut.model_validate(a)
        o.ticket_id = (result or {}).get("ticket_id") if a.status in ("approved", "modified") else None
        out.append(o)
    return out


async def _pending(session, project, aid: str) -> Approval:
    a = await session.get(Approval, aid)
    if a is None or a.project_id != project.id:
        raise HTTPException(404, "Approval not found")
    if a.status != "pending":
        raise HTTPException(409, f"Approval already {a.status}")
    return a


@router.post("/{aid}/approve", response_model=ApprovalOut)
async def approve(aid: str, project: ProjectDep, session: Session):
    a = await _pending(session, project, aid)
    await run_service.resolve_approval(session, project, a, "y", "approved")
    await session.commit()
    return a


@router.post("/{aid}/reject", response_model=ApprovalOut)
async def reject(aid: str, project: ProjectDep, session: Session):
    a = await _pending(session, project, aid)
    await run_service.resolve_approval(session, project, a, "n", "rejected")
    await session.commit()
    return a


@router.post("/{aid}/modify", response_model=ApprovalOut)
async def modify(aid: str, body: ApprovalModifyIn, project: ProjectDep, session: Session):
    a = await _pending(session, project, aid)
    await run_service.resolve_approval(session, project, a, body.severity, "modified")
    await session.commit()
    return a
