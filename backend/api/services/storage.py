"""Project files: metadata in the `files` table, bytes in a storage backend.

Backends: local disk (dev, single replica) or any S3-compatible bucket
(Railway with several API replicas — they cannot share a volume). Object keys
are opaque (`projects/{id}/{uuid}`), so rename/move never copies bytes."""

from __future__ import annotations

import asyncio
import mimetypes
import re
import shutil
from pathlib import Path
from typing import Optional, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.ids import uid
from ..models import File, Project

DEFAULT_FOLDERS = ["docs", "requirements", "architecture", "logs", "uploads", "out"]


# ------------------------------------------------------------- backends ----
class Backend(Protocol):
    async def put(self, key: str, data: bytes, mime: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def delete_prefix(self, prefix: str) -> None: ...


class LocalBackend:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _p(self, key: str) -> Path:
        return self.root / key

    async def put(self, key: str, data: bytes, mime: str) -> None:
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(p.write_bytes, data)

    async def get(self, key: str) -> bytes:
        p = self._p(key)
        return await asyncio.to_thread(p.read_bytes) if p.exists() else b""

    async def delete(self, key: str) -> None:
        p = self._p(key)
        if p.exists():
            p.unlink()

    async def delete_prefix(self, prefix: str) -> None:
        await asyncio.to_thread(shutil.rmtree, self._p(prefix), True)


class S3Backend:
    def __init__(self) -> None:
        import boto3

        kw = {"region_name": settings.S3_REGION}
        if settings.S3_ENDPOINT_URL:
            kw["endpoint_url"] = settings.S3_ENDPOINT_URL
        if settings.S3_ACCESS_KEY_ID:
            kw["aws_access_key_id"] = settings.S3_ACCESS_KEY_ID
            kw["aws_secret_access_key"] = settings.S3_SECRET_ACCESS_KEY
        self.client = boto3.client("s3", **kw)
        self.bucket = settings.S3_BUCKET

    async def put(self, key: str, data: bytes, mime: str) -> None:
        await asyncio.to_thread(self.client.put_object, Bucket=self.bucket, Key=key, Body=data, ContentType=mime)

    async def get(self, key: str) -> bytes:
        def _get():
            try:
                return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            except self.client.exceptions.NoSuchKey:
                return b""
        return await asyncio.to_thread(_get)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def delete_prefix(self, prefix: str) -> None:
        def _rm():
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
                if keys:
                    self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys})
        await asyncio.to_thread(_rm)


_backend: Optional[Backend] = None


def backend() -> Backend:
    global _backend
    if _backend is None:
        _backend = S3Backend() if settings.STORAGE_BACKEND == "s3" else LocalBackend(settings.TRIAGE_DATA_DIR / "blobs")
    return _backend


# ------------------------------------------------------------------ paths --
def safe_name(name: str) -> str:
    name = re.sub(r"[^\w.\- ()]+", "_", name.strip()) or "file"
    return name[:200]


def norm_path(path: str) -> str:
    parts = [p for p in path.replace("\\", "/").split("/") if p and p not in (".", "..")]
    return "/" + "/".join(parts)


def guess_mime(name: str) -> str:
    m, _ = mimetypes.guess_type(name)
    if m:
        return m
    if name.lower().endswith((".md", ".markdown")):
        return "text/markdown"
    if name.upper() == "CODEOWNERS" or name.lower().endswith((".txt", ".log", ".csv")):
        return "text/plain"
    return "application/octet-stream"


def _key(project_id: str) -> str:
    return f"projects/{project_id}/{uid()}"


# ------------------------------------------------------------------- rows --
async def ensure_layout(session: AsyncSession, project: Project) -> None:
    existing = {r.path for r in (await session.execute(select(File).where(File.project_id == project.id, File.kind == "dir"))).scalars()}
    for folder in DEFAULT_FOLDERS:
        p = f"/{folder}"
        if p not in existing:
            session.add(File(project_id=project.id, path=p, name=folder, kind="dir"))
    await session.flush()


async def ensure_dir(session: AsyncSession, project: Project, path: str) -> None:
    path = norm_path(path)
    if path == "/":
        return
    parts = path.strip("/").split("/")
    for i in range(1, len(parts) + 1):
        p = "/" + "/".join(parts[:i])
        row = (await session.execute(select(File).where(File.project_id == project.id, File.path == p))).scalar_one_or_none()
        if row is None:
            session.add(File(project_id=project.id, path=p, name=parts[i - 1], kind="dir"))
            await session.flush()


async def write_file(session: AsyncSession, project: Project, path: str, data: bytes, mime: Optional[str] = None) -> File:
    """Create or replace a file at a virtual path."""
    path = norm_path(path)
    name = path.rsplit("/", 1)[-1]
    await ensure_dir(session, project, path.rsplit("/", 1)[0] or "/")
    row = (await session.execute(select(File).where(File.project_id == project.id, File.path == path))).scalar_one_or_none()
    mime = mime or guess_mime(name)
    key = _key(project.id)
    await backend().put(key, data, mime)
    if row is None:
        row = File(project_id=project.id, path=path, name=name, kind="file")
        session.add(row)
    elif row.storage_key:
        await backend().delete(row.storage_key)
    row.size_bytes, row.mime, row.storage_key = len(data), mime, key
    await session.flush()
    return row


async def read_bytes(row: File) -> bytes:
    return await backend().get(row.storage_key) if row.storage_key else b""


async def delete_path(session: AsyncSession, project: Project, row: File) -> None:
    if row.kind == "dir":
        children = (await session.execute(select(File).where(File.project_id == project.id, File.path.like(row.path.rstrip("/") + "/%")))).scalars().all()
        for c in children:
            if c.storage_key:
                await backend().delete(c.storage_key)
            await session.delete(c)
    elif row.storage_key:
        await backend().delete(row.storage_key)
    await session.delete(row)
    await session.flush()


async def move_path(session: AsyncSession, project: Project, row: File, new_path: str) -> File:
    new_path = norm_path(new_path)
    old_path = row.path
    await ensure_dir(session, project, new_path.rsplit("/", 1)[0] or "/")
    if row.kind == "dir":
        children = (await session.execute(select(File).where(File.project_id == project.id, File.path.like(old_path.rstrip("/") + "/%")))).scalars().all()
        for c in children:
            c.path = new_path + c.path[len(old_path):]
    row.path = new_path
    row.name = new_path.rsplit("/", 1)[-1]
    await session.flush()
    return row


async def remove_project_storage(project_id: str) -> None:
    await backend().delete_prefix(f"projects/{project_id}/")
