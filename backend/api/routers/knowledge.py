from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, UploadFile
from sqlalchemy import select

from ..core.deps import CurrentUser, ProjectDep, Session
from ..models import KnowledgeItem, UserSettings
from ..schemas import KnowledgeOut, KnowledgeTextIn, KnowledgeUrlIn
from ..services import knowledge
from ..services.llm import ResolvedLlmConfig

router = APIRouter(prefix="/api/projects/{project_id}/knowledge", tags=["knowledge"])
MAX_UPLOAD = 25 * 1024 * 1024


@router.get("", response_model=list[KnowledgeOut])
async def list_items(project: ProjectDep, session: Session):
    return (await session.execute(select(KnowledgeItem).where(KnowledgeItem.project_id == project.id).order_by(KnowledgeItem.created_at.desc()))).scalars().all()


@router.post("/upload", response_model=list[KnowledgeOut], status_code=201)
async def upload(project: ProjectDep, session: Session, files: list[UploadFile], kind: str = Form("auto")):
    items = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, f"{f.filename} is larger than 25 MB")
        items.append(await knowledge.create_item(session, project, name=f.filename or "upload", data=data, kind=kind))
    await session.commit()
    for it in items:
        knowledge.schedule_index(project.id, it.id)
    return items


@router.post("/url", response_model=KnowledgeOut, status_code=201)
async def add_url(body: KnowledgeUrlIn, project: ProjectDep, session: Session):
    try:
        _, data = await knowledge.fetch_url(body.url)
    except Exception as exc:
        raise HTTPException(422, f"Could not fetch URL: {exc}")
    name = body.name or body.url.rstrip("/").rsplit("/", 1)[-1] or body.url
    if not name.endswith(".txt"):
        name = name[:80] + ".txt"
    item = await knowledge.create_item(session, project, name=name, data=data, kind="url", source_url=body.url)
    await session.commit()
    knowledge.schedule_index(project.id, item.id)
    return item


@router.post("/text", response_model=KnowledgeOut, status_code=201)
async def add_text(body: KnowledgeTextIn, project: ProjectDep, session: Session):
    name = body.name if "." in body.name else body.name + ".md"
    item = await knowledge.create_item(session, project, name=name, data=body.text.encode(), kind=body.kind, folder="/docs")
    await session.commit()
    knowledge.schedule_index(project.id, item.id)
    return item


@router.post("/{kid}/reindex", response_model=KnowledgeOut)
async def reindex(kid: str, project: ProjectDep, session: Session):
    it = await session.get(KnowledgeItem, kid)
    if it is None or it.project_id != project.id:
        raise HTTPException(404, "Knowledge item not found")
    it.status, it.progress, it.error = "indexing", 0, None
    await session.commit()
    knowledge.schedule_index(project.id, it.id)
    return it


@router.delete("/{kid}", status_code=204)
async def delete_item(kid: str, project: ProjectDep, user: CurrentUser, session: Session):
    it = await session.get(KnowledgeItem, kid)
    if it is None or it.project_id != project.id:
        raise HTTPException(404, "Knowledge item not found")
    cfg = ResolvedLlmConfig.from_settings(await session.get(UserSettings, user.id))
    await knowledge.delete_item(session, project, it, cfg)
    await session.commit()
