from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from triage.tools.registry import TOOLS

from ..core.deps import ProjectDep, Session
from ..models import Agent, RunEvent, ToolCallRow, Run
from ..schemas import AgentIn, AgentOut, AgentPatch
from ..services import activity

router = APIRouter(prefix="/api/projects/{project_id}/agents", tags=["agents"])


def _check_tools(tools: list[str]) -> None:
    bad = [t for t in tools if t not in TOOLS]
    if bad:
        raise HTTPException(422, f"Unknown tools: {', '.join(bad)}")


@router.get("", response_model=list[AgentOut])
async def list_agents(project: ProjectDep, session: Session):
    return (await session.execute(select(Agent).where(Agent.project_id == project.id).order_by(Agent.position, Agent.created_at))).scalars().all()


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(body: AgentIn, project: ProjectDep, session: Session):
    _check_tools(body.tools)
    if (await session.execute(select(Agent.id).where(Agent.project_id == project.id, Agent.name == body.name))).first():
        raise HTTPException(409, f"Agent '{body.name}' already exists in this project")
    a = Agent(project_id=project.id, **body.model_dump())
    session.add(a)
    await session.flush()
    await activity.log(session, project, "AGENT", f"initialized {a.name}", ref_type="agent", ref_id=a.id)
    await session.commit()
    return a


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: str, project: ProjectDep, session: Session):
    a = await session.get(Agent, agent_id)
    if a is None or a.project_id != project.id:
        raise HTTPException(404, "Agent not found")
    return a


@router.patch("/{agent_id}", response_model=AgentOut)
async def patch_agent(agent_id: str, body: AgentPatch, project: ProjectDep, session: Session):
    a = await session.get(Agent, agent_id)
    if a is None or a.project_id != project.id:
        raise HTTPException(404, "Agent not found")
    changes = body.model_dump(exclude_unset=True)
    if "tools" in changes and changes["tools"] is not None:
        _check_tools(changes["tools"])
    for k, v in changes.items():
        if v is not None or k == "model":
            setattr(a, k, v)
    await activity.log(session, project, "AGENT", f"updated {a.name}", ref_type="agent", ref_id=a.id)
    await session.commit()
    return a


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, project: ProjectDep, session: Session):
    a = await session.get(Agent, agent_id)
    if a is None or a.project_id != project.id:
        raise HTTPException(404, "Agent not found")
    await activity.log(session, project, "AGENT", f"removed {a.name}", ref_type="agent", ref_id=a.id)
    await session.delete(a)
    await session.commit()


@router.get("/{agent_id}/detail")
async def agent_detail(agent_id: str, project: ProjectDep, session: Session):
    """Right-hand panel of the agent page: current task, memory used, files, tools, handoffs."""
    a = await session.get(Agent, agent_id)
    if a is None or a.project_id != project.id:
        raise HTTPException(404, "Agent not found")
    name = a.name
    live = (await session.execute(select(Run).where(Run.project_id == project.id, Run.status.in_(("running", "waiting_approval")), Run.current_agent == name).order_by(Run.started_at.desc()).limit(1))).scalar_one_or_none()
    last_run = live or (await session.execute(
        select(Run).join(RunEvent, RunEvent.run_id == Run.id).where(Run.project_id == project.id, RunEvent.actor == name.upper()).order_by(Run.started_at.desc()).limit(1)
    )).scalar_one_or_none()
    events = []
    if last_run:
        events = (await session.execute(select(RunEvent).where(RunEvent.run_id == last_run.id).order_by(RunEvent.seq))).scalars().all()
    mine = [e for e in events if e.actor == name.upper() or (e.kind == "TOOL_RESULT" and e.meta.get("tool_id") in {x.meta.get("tool_id") for x in events if x.actor == name.upper()})]
    tool_counts = (await session.execute(
        select(ToolCallRow.tool_name, func.count()).where(ToolCallRow.project_id == project.id, ToolCallRow.agent_name == name).group_by(ToolCallRow.tool_name)
    )).all()
    handoffs = (await session.execute(
        select(RunEvent).where(RunEvent.project_id == project.id, RunEvent.kind == "HANDOFF").order_by(RunEvent.ts.desc()).limit(50)
    )).scalars().all()
    handoffs = [h for h in handoffs if h.meta.get("from") == name or h.meta.get("to") == name][:12]
    memory_events = [e for e in events if e.kind == "MEMORY"]
    files = [e.message.replace("artifact ", "") for e in events if e.kind == "SYSTEM" and e.message.startswith("artifact ")]
    return {
        "agent": AgentOut.model_validate(a),
        "run": {"id": last_run.id, "status": last_run.status, "task_id": last_run.task_id, "current_agent": last_run.current_agent} if last_run else None,
        "events": [{"id": e.id, "seq": e.seq, "ts": e.ts, "kind": e.kind, "actor": e.actor, "message": e.message, "meta": e.meta, "duration_ms": e.duration_ms} for e in mine[-80:]],
        "memory_used": [m.message for m in memory_events][-10:],
        "files_accessed": files,
        "tools_called": [{"tool": t, "count": n} for t, n in tool_counts],
        "handoffs": [{"run_id": h.run_id, "ts": h.ts, "from": h.meta.get("from"), "to": h.meta.get("to")} for h in handoffs],
    }
