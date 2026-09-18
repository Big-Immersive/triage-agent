from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from ..core.deps import ProjectDep, Session
from ..models import File
from ..schemas import FileMkdirIn, FileMoveIn, FileOut
from ..services import activity, storage

router = APIRouter(prefix="/api/projects/{project_id}/files", tags=["files"])
PREVIEW_MAX = 512 * 1024
TEXT_MIMES = ("text/", "application/json", "application/xml", "application/javascript", "application/x-yaml")


@router.get("", response_model=list[FileOut])
async def list_files(project: ProjectDep, session: Session):
    await storage.ensure_layout(session, project)
    await session.commit()
    return (await session.execute(select(File).where(File.project_id == project.id).order_by(File.path))).scalars().all()


@router.post("/upload", response_model=list[FileOut], status_code=201)
async def upload(project: ProjectDep, session: Session, files: list[UploadFile], folder: str = Form("/uploads")):
    out = []
    for f in files:
        data = await f.read()
        row = await storage.write_file(session, project, f"{storage.norm_path(folder)}/{storage.safe_name(f.filename or 'file')}", data, f.content_type)
        await activity.log(session, project, "FILE", f"uploaded {row.path}", ref_type="file", ref_id=row.id)
        out.append(row)
    await session.commit()
    return out


@router.post("/mkdir", response_model=FileOut, status_code=201)
async def mkdir(body: FileMkdirIn, project: ProjectDep, session: Session):
    path = storage.norm_path(body.path)
    await storage.ensure_dir(session, project, path)
    row = (await session.execute(select(File).where(File.project_id == project.id, File.path == path))).scalar_one()
    await session.commit()
    return row


async def _get(session, project, fid: str) -> File:
    row = await session.get(File, fid)
    if row is None or row.project_id != project.id:
        raise HTTPException(404, "File not found")
    return row


@router.get("/{fid}/content")
async def content(fid: str, project: ProjectDep, session: Session, download: bool = False):
    row = await _get(session, project, fid)
    if row.kind != "file":
        raise HTTPException(400, "Not a file")
    data = await storage.read_bytes(row)
    headers = {"Content-Disposition": f'{"attachment" if download else "inline"}; filename="{row.name}"'}
    return Response(content=data, media_type=row.mime, headers=headers)


@router.get("/{fid}/preview")
async def preview(fid: str, project: ProjectDep, session: Session):
    row = await _get(session, project, fid)
    if row.kind != "file":
        raise HTTPException(400, "Not a file")
    if not row.mime.startswith(TEXT_MIMES) and row.mime != "application/octet-stream":
        return {"id": row.id, "mime": row.mime, "text": None, "previewable": row.mime == "application/pdf"}
    data = await storage.read_bytes(row)
    text = data[:PREVIEW_MAX].decode("utf-8", errors="replace")
    return {"id": row.id, "mime": row.mime, "text": text, "truncated": len(data) > PREVIEW_MAX, "previewable": True}


@router.post("/{fid}/move", response_model=FileOut)
async def move(fid: str, body: FileMoveIn, project: ProjectDep, session: Session):
    row = await _get(session, project, fid)
    new_path = storage.norm_path(body.new_path)
    if (await session.execute(select(File.id).where(File.project_id == project.id, File.path == new_path))).first():
        raise HTTPException(409, "Target path exists")
    old = row.path
    await storage.move_path(session, project, row, new_path)
    await activity.log(session, project, "FILE", f"moved {old} → {row.path}", ref_type="file", ref_id=row.id)
    await session.commit()
    return row


@router.delete("/{fid}", status_code=204)
async def delete(fid: str, project: ProjectDep, session: Session):
    row = await _get(session, project, fid)
    path = row.path
    await storage.delete_path(session, project, row)
    await activity.log(session, project, "FILE", f"deleted {path}", ref_type="file", ref_id=fid)
    await session.commit()
