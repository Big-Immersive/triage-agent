from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from ..core.deps import CurrentUser, ProjectDep, Session, slugify
from ..models import Activity, Agent, Approval, KnowledgeItem, Memory, Project, Run, Task, now
from ..schemas import ProjectIn, ProjectOut, ProjectPatch
from ..services import activity, runtimes, storage
from ..services.runs import run_service
from ..templates import bug_triage
from ..core.bus import bus

router = APIRouter(prefix="/api/projects", tags=["projects"])
ACTIVE_RUN = ("queued", "running", "waiting_approval")
ONLINE = ("thinking", "running", "tool_call", "waiting", "human_input")


async def _stats(session, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    out = {i: {"agents_total": 0, "agents_online": 0, "runs_active": 0, "approvals_pending": 0} for i in ids}
    for pid, total, online in (await session.execute(
        select(Agent.project_id, func.count(), func.sum(func.cast(Agent.status.in_(ONLINE), type_=__import__("sqlalchemy").Integer)))
        .where(Agent.project_id.in_(ids)).group_by(Agent.project_id)
    )).all():
        out[pid]["agents_total"], out[pid]["agents_online"] = total, int(online or 0)
    for pid, n in (await session.execute(select(Run.project_id, func.count()).where(Run.project_id.in_(ids), Run.status.in_(ACTIVE_RUN)).group_by(Run.project_id))).all():
        out[pid]["runs_active"] = n
    for pid, n in (await session.execute(select(Approval.project_id, func.count()).where(Approval.project_id.in_(ids), Approval.status == "pending").group_by(Approval.project_id))).all():
        out[pid]["approvals_pending"] = n
    return out


def _out(p: Project, st: dict) -> ProjectOut:
    o = ProjectOut.model_validate(p)
    o.config = {k: v for k, v in (p.config or {}).items() if k != "intake_key_hash"}
    for k, v in st.items():
        setattr(o, k, v)
    return o


async def _unique_slug(session, user_id: str, name: str) -> str:
    base = slugify(name)
    slug, i = base, 2
    while (await session.execute(select(Project.id).where(Project.owner_id == user_id, Project.slug == slug))).first():
        slug = f"{base}-{i}"
        i += 1
    return slug


@router.get("", response_model=list[ProjectOut])
async def list_projects(user: CurrentUser, session: Session, include_archived: bool = False):
    q = select(Project).where(Project.owner_id == user.id)
    if not include_archived:
        q = q.where(Project.status != "archived")
    rows = (await session.execute(q.order_by(Project.last_activity_at.desc()))).scalars().all()
    st = await _stats(session, [p.id for p in rows])
    return [_out(p, st[p.id]) for p in rows]


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectIn, user: CurrentUser, session: Session):
    p = Project(owner_id=user.id, name=body.name.strip(), slug=await _unique_slug(session, user.id, body.name), description=body.description,
                icon=body.icon or "▣", instructions=body.instructions, status="draft" if body.template is None else "active")
    session.add(p)
    await session.flush()
    await storage.ensure_layout(session, p)
    await activity.log(session, p, "PROJECT", "created", ref_type="project", ref_id=p.id)
    created = None
    if body.template == "bug-triage":
        created = await bug_triage.apply_all(session, p)
    await session.commit()
    for kid in (created or {}).get("knowledge", []):
        from ..services import knowledge
        knowledge.schedule_index(p.id, kid)
    st = await _stats(session, [p.id])
    return _out(p, st[p.id])


@router.get("/{project_id}", response_model=ProjectOut)
async def get_one(project: ProjectDep, session: Session):
    st = await _stats(session, [project.id])
    return _out(project, st[project.id])


@router.patch("/{project_id}", response_model=ProjectOut)
async def patch_project(body: ProjectPatch, project: ProjectDep, session: Session):
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"].strip() and changes["name"].strip() != project.name:
        project.name = changes["name"].strip()
        project.slug = await _unique_slug(session, project.owner_id, project.name)
        await activity.log(session, project, "PROJECT", f"renamed to {project.name}", ref_type="project", ref_id=project.id)
    for k in ("description", "icon", "instructions", "status"):
        if k in changes and changes[k] is not None:
            setattr(project, k, changes[k])
    if changes.get("config") is not None:
        keep = {k: v for k, v in (project.config or {}).items() if k.startswith("intake_key")}
        project.config = {**{k: v for k, v in changes["config"].items() if not k.startswith("intake_key")}, **keep}
    if "status" in changes:
        await activity.log(session, project, "PROJECT", f"status → {project.status}", ref_type="project", ref_id=project.id)
    await session.commit()
    st = await _stats(session, [project.id])
    return _out(project, st[project.id])


@router.post("/{project_id}/archive", response_model=ProjectOut)
async def archive(project: ProjectDep, session: Session):
    project.status = "archived"
    await activity.log(session, project, "PROJECT", "archived", ref_type="project", ref_id=project.id)
    await session.commit()
    st = await _stats(session, [project.id])
    return _out(project, st[project.id])


@router.post("/{project_id}/activate", response_model=ProjectOut)
async def activate(project: ProjectDep, session: Session):
    project.status = "active"
    await activity.log(session, project, "PROJECT", "initialized", ref_type="project", ref_id=project.id)
    await session.commit()
    st = await _stats(session, [project.id])
    return _out(project, st[project.id])


@router.delete("/{project_id}", status_code=204)
async def delete_project(project: ProjectDep, session: Session):
    live = (await session.execute(select(Run).where(Run.project_id == project.id, Run.status.in_(ACTIVE_RUN)))).scalars().all()
    for run in live:
        await run_service.request_cancel(session, project, run)
    runtimes.invalidate(project.id)
    await bus.publish(session, "system", "runtime.invalidate", {"project_id": project.id})
    pid = project.id
    await session.delete(project)
    await session.commit()
    await storage.remove_project_storage(pid)
    await runtimes.purge_vectors(pid)


@router.post("/{project_id}/sample-data")
async def load_sample_data(project: ProjectDep, session: Session, agents: bool = True, knowledge_items: bool = True, tasks: bool = True):
    created = await bug_triage.apply_all(session, project, agents=agents, knowledge_items=knowledge_items, tasks=tasks)
    if project.status == "draft":
        project.status = "active"
    await session.commit()
    from ..services import knowledge
    for kid in created["knowledge"]:
        knowledge.schedule_index(project.id, kid)
    return {"agents": created["agents"], "knowledge": len(created["knowledge"]), "tasks": created["tasks"]}


@router.get("/{project_id}/overview")
async def overview(project: ProjectDep, session: Session):
    pid = project.id
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    agents = (await session.execute(select(Agent).where(Agent.project_id == pid).order_by(Agent.position))).scalars().all()
    counts = {
        "agents_total": len(agents),
        "agents_enabled": sum(a.enabled for a in agents),
        "agents_online": sum(a.status in ONLINE for a in agents),
        "running_tasks": (await session.execute(select(func.count()).where(Task.project_id == pid, Task.status.in_(("queued", "running"))))).scalar(),
        "queued_tasks": (await session.execute(select(func.count()).where(Task.project_id == pid, Task.status == "queued"))).scalar(),
        "runs_today": (await session.execute(select(func.count()).where(Run.project_id == pid, Run.started_at >= today))).scalar(),
        "runs_active": (await session.execute(select(func.count()).where(Run.project_id == pid, Run.status.in_(ACTIVE_RUN)))).scalar(),
        "waiting_approval": (await session.execute(select(func.count()).where(Approval.project_id == pid, Approval.status == "pending"))).scalar(),
        "memory_records": (await session.execute(select(func.count()).where(Memory.project_id == pid))).scalar(),
        "knowledge_items": (await session.execute(select(func.count()).where(KnowledgeItem.project_id == pid))).scalar(),
        "knowledge_ready": (await session.execute(select(func.count()).where(KnowledgeItem.project_id == pid, KnowledgeItem.status == "ready"))).scalar(),
        "knowledge_indexing": (await session.execute(select(func.count()).where(KnowledgeItem.project_id == pid, KnowledgeItem.status == "indexing"))).scalar(),
    }
    recent = (await session.execute(select(Activity).where(Activity.project_id == pid).order_by(Activity.ts.desc()).limit(40))).scalars().all()
    runs = (await session.execute(select(Run).where(Run.project_id == pid).order_by(Run.started_at.desc()).limit(8))).scalars().all()
    return {
        "counts": counts,
        "agents": [{"id": a.id, "name": a.name, "role": a.role, "status": a.status, "current_process": a.current_process, "enabled": a.enabled} for a in agents],
        "activity": [{"id": r.id, "ts": r.ts, "category": r.category, "message": r.message, "ref_type": r.ref_type, "ref_id": r.ref_id} for r in reversed(recent)],
        "recent_runs": [{"id": r.id, "status": r.status, "current_agent": r.current_agent, "started_at": r.started_at, "duration_ms": r.duration_ms} for r in runs],
        "memory_synced": counts["knowledge_indexing"] == 0,
    }


@router.get("/{project_id}/graph")
async def graph(project: ProjectDep, session: Session):
    agents = (await session.execute(select(Agent).where(Agent.project_id == project.id).order_by(Agent.position))).scalars().all()
    names = {a.name for a in agents}
    live = (await session.execute(select(Run).where(Run.project_id == project.id, Run.status.in_(ACTIVE_RUN)).order_by(Run.started_at.desc()).limit(1))).scalar_one_or_none()
    last_handoff = None
    if live:
        from ..models import RunEvent
        ev = (await session.execute(select(RunEvent).where(RunEvent.run_id == live.id, RunEvent.kind == "HANDOFF").order_by(RunEvent.seq.desc()).limit(1))).scalar_one_or_none()
        if ev:
            last_handoff = ev.meta
    return {
        "nodes": [{"id": a.name, "agent_id": a.id, "name": a.name, "role": a.role, "status": a.status if a.enabled else "disabled", "current_process": a.current_process, "enabled": a.enabled} for a in agents],
        "edges": [{"id": f"{a.name}->{t}", "source": a.name, "target": t} for a in agents for t in (a.can_handoff_to or []) if t in names],
        "active_run": live.id if live else None,
        "active_agent": live.current_agent if live else None,
        "last_handoff": last_handoff,
    }
