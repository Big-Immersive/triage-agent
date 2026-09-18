"""The 'bug-triage' template: the four demo agents, the Orbit Run fixtures as
knowledge, and the 15 inbox items as tasks. Applied only when a user asks
(wizard button or LOAD SAMPLE DATASET) — never on its own."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from triage import settings as engine_settings
from triage.agents import DEFAULT_AGENTS

from ..models import Agent, KnowledgeItem, Project, Task
from ..services import activity, knowledge

FIXTURE_FILES = [
    ("tickets.json", "tracker", "/uploads/tickets.json"),
    ("crashes.csv", "crashlog", "/uploads/crashes.csv"),
    ("releases.json", "releases", "/uploads/releases.json"),
    ("CODEOWNERS", "codeowners", "/uploads/CODEOWNERS"),
]

SAMPLE_INSTRUCTIONS = (
    "Orbit Run is a free-to-play mobile game (iOS + Android) by Nebula Games. Current release line is 2.4.x. "
    "Feedback arrives from store reviews, Discord, support email and the in-app form. Billing and data-loss "
    "problems are always at least high severity."
)


async def apply_agents(session: AsyncSession, project: Project) -> int:
    existing = {a.name for a in (await session.execute(select(Agent).where(Agent.project_id == project.id))).scalars()}
    n = 0
    for i, spec in enumerate(DEFAULT_AGENTS):
        if spec.name in existing:
            continue
        session.add(Agent(project_id=project.id, name=spec.name, role=spec.role, description=spec.description, instructions=spec.instructions,
                          tools=list(spec.tools), can_handoff_to=list(spec.can_handoff_to), enabled=True, position=i,
                          permissions={"side_effects": spec.name == "writer", "requires_approval": spec.name == "writer"}))
        n += 1
    await session.flush()
    if n:
        await activity.log(session, project, "AGENT", f"initialized {n} template agents", ref_type="project", ref_id=project.id)
    return n


async def apply_knowledge(session: AsyncSession, project: Project) -> list[str]:
    existing = {k.name for k in (await session.execute(select(KnowledgeItem).where(KnowledgeItem.project_id == project.id))).scalars()}
    created = []
    for fname, kind, _ in FIXTURE_FILES:
        if fname in existing:
            continue
        data = (engine_settings.FIXTURES_DIR / fname).read_bytes()
        item = await knowledge.create_item(session, project, name=fname, data=data, kind=kind, folder="/uploads")
        created.append(item.id)
    return created


async def apply_tasks(session: AsyncSession, project: Project) -> int:
    existing = {t.external_id for t in (await session.execute(select(Task).where(Task.project_id == project.id))).scalars()}
    n = 0
    for p in sorted(engine_settings.INBOX_DIR.glob("*.json")):
        fb = json.loads(p.read_text())
        if fb["id"] in existing:
            continue
        session.add(Task(project_id=project.id, external_id=fb["id"], source=fb.get("source", "sample"), author=fb.get("author", ""),
                         title=fb["text"][:80].replace("\n", " "), text=fb["text"], rating=fb.get("rating"),
                         received_at=fb.get("received_at"), meta=fb.get("metadata") or {}, status="queued"))
        n += 1
    await session.flush()
    if n:
        await activity.log(session, project, "SYSTEM", f"imported {n} sample tasks", ref_type="project", ref_id=project.id)
    return n


async def apply_all(session: AsyncSession, project: Project, *, agents: bool = True, knowledge_items: bool = True, tasks: bool = True) -> dict:
    out = {"agents": 0, "knowledge": [], "tasks": 0}
    if agents:
        out["agents"] = await apply_agents(session, project)
    if knowledge_items:
        out["knowledge"] = await apply_knowledge(session, project)
    if tasks:
        out["tasks"] = await apply_tasks(session, project)
    if not project.instructions.strip():
        project.instructions = SAMPLE_INSTRUCTIONS
    return out
