"""Knowledge items: store the source bytes as a project file, detect the kind,
and index in the background with progress events.

Structured kinds (tracker / crashlog / releases / codeowners) feed the agent
tools directly; text kinds are chunked and embedded into the project's
knowledge collection."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.bus import bus
from ..core.db import SessionLocal
from ..models import File, KnowledgeItem, Project, User, UserSettings
from . import activity, runtimes, storage
from .llm import ResolvedLlmConfig

log = logging.getLogger("triage.knowledge")
_index_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)   # one indexing job per project at a time (per process)


def detect_kind(name: str, data: bytes, declared: Optional[str] = None) -> str:
    if declared and declared != "auto":
        return declared
    n = name.lower()
    head = data[:4000].decode("utf-8", errors="ignore")
    if n == "codeowners" or n.endswith("codeowners"):
        return "codeowners"
    if n.endswith(".csv"):
        try:
            cols = next(csv.reader(io.StringIO(head)))
            if "signature" in cols and "app_version" in cols:
                return "crashlog"
        except StopIteration:
            pass
        return "document"
    if n.endswith(".json"):
        try:
            obj = json.loads(data.decode("utf-8", errors="ignore"))
        except Exception:
            return "document"
        if isinstance(obj, list) and obj and isinstance(obj[0], dict) and {"id", "title"} <= set(obj[0]):
            return "tracker"
        if isinstance(obj, dict) and "tickets" in obj:
            return "tracker"
        if isinstance(obj, dict) and ("releases" in obj or "current_version" in obj):
            return "releases"
        return "code"
    if n.endswith(".pdf") or data[:5] == b"%PDF-":
        return "pdf"
    if n.endswith((".docx", ".doc", ".rtf", ".txt")):
        return "document"
    if n.endswith((".md", ".markdown")):
        return "markdown"
    if n.endswith((".py", ".ts", ".tsx", ".js", ".go", ".rs", ".java", ".kt", ".swift", ".yaml", ".yml", ".toml")):
        return "code"
    return "document"


def _docx_text(data: bytes) -> str:
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def extract_text(kind: str, name: str, data: bytes) -> str:
    """Text for embedding. Sniffs the bytes, so a PDF uploaded as 'document' still works,
    and strips NUL / control characters Postgres refuses."""
    n = name.lower()
    if kind == "pdf" or data[:5] == b"%PDF-" or n.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    elif data[:2] == b"PK" and (n.endswith(".docx") or b"word/document.xml" in data[:4000]):
        text = _docx_text(data)
    else:
        text = data.decode("utf-8", errors="replace")
        # Mostly undecodable => a binary we do not understand (xls, images, ...).
        if len(text) > 200 and text.count("\ufffd") / len(text) > 0.1:
            raise ValueError(f"{name} looks like a binary file; upload PDF, DOCX or plain text")
    return clean_text(text)


def clean_text(text: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text).replace("\ufffd", "")


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


async def fetch_url(url: str) -> tuple[str, bytes]:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": "triage-dashboard/0.1"}) as c:
        r = await c.get(url)
        r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    if "html" in ctype:
        return "text/plain", _strip_html(r.text).encode()
    return ctype.split(";")[0] or "application/octet-stream", r.content


async def create_item(
    session: AsyncSession, project: Project, *, name: str, data: bytes, kind: Optional[str] = None,
    folder: str = "/uploads", source_url: Optional[str] = None,
) -> KnowledgeItem:
    kind = detect_kind(name, data, kind)
    row = await storage.write_file(session, project, f"{folder}/{storage.safe_name(name)}", data)
    item = KnowledgeItem(project_id=project.id, name=name, kind=kind, size_bytes=len(data), status="indexing", progress=0, file_id=row.id, source_url=source_url)
    session.add(item)
    await session.flush()
    await activity.log(session, project, "KNOWLEDGE", f"added {name} ({kind})", ref_type="knowledge", ref_id=item.id)
    await activity.log(session, project, "FILE", f"uploaded {row.path}", ref_type="file", ref_id=row.id)
    return item


async def _progress(session: AsyncSession, project: Project, item: KnowledgeItem) -> None:
    await bus.publish_project(session, project.id, project.owner_id, "knowledge.progress", {
        "id": item.id, "name": item.name, "kind": item.kind, "status": item.status, "progress": item.progress, "error": item.error,
    })
    await session.commit()


_jobs: set[asyncio.Task] = set()


def schedule_index(project_id: str, item_id: str) -> None:
    t = asyncio.create_task(index_item(project_id, item_id))
    _jobs.add(t)
    t.add_done_callback(_jobs.discard)


async def wait_idle() -> None:
    """Tests / shutdown: let in-flight indexing jobs finish."""
    while _jobs:
        await asyncio.gather(*list(_jobs), return_exceptions=True)


async def index_item(project_id: str, item_id: str) -> None:
    async with _index_locks[project_id]:
        await _index_item(project_id, item_id)


async def _index_item(project_id: str, item_id: str) -> None:
    async with SessionLocal() as session:
        project = await session.get(Project, project_id)
        item = await session.get(KnowledgeItem, item_id)
        if project is None or item is None:
            return
        owner = await session.get(User, project.owner_id)
        us = await session.get(UserSettings, owner.id) if owner else None
        cfg = ResolvedLlmConfig.from_settings(us)
        try:
            ok, why = cfg.ready()
            if not ok:
                raise RuntimeError(why)
            await activity.log(session, project, "KNOWLEDGE", f"indexing started {item.name}", ref_type="knowledge", ref_id=item.id)
            await session.commit()
            frow = await session.get(File, item.file_id) if item.file_id else None
            data = await storage.read_bytes(frow) if frow else b""

            if item.kind in runtimes.STRUCTURED_KINDS:
                if item.kind in ("tracker", "releases"):
                    json.loads(data.decode("utf-8"))
                elif item.kind == "crashlog":
                    next(csv.reader(io.StringIO(data.decode("utf-8"))))
                item.status, item.progress = "ready", 100
                item.indexed_at = datetime.now(timezone.utc)
                await session.commit()
                # Rebuild this replica's runtime (re-embedding the tracker if it changed) and tell the others to drop theirs.
                await runtimes.get_runtime(session, project, cfg, reindex_tickets=item.kind == "tracker")
                await bus.publish(session, "system", "runtime.invalidate", {"project_id": project.id})
            else:
                text = extract_text(item.kind, item.name, data)
                if not text.strip():
                    raise ValueError("no extractable text")
                rt = await runtimes.get_runtime(session, project, cfg)
                loop = asyncio.get_running_loop()
                last = {"pct": 0}

                def cb(i: int, total: int) -> None:
                    pct = int(i * 100 / max(total, 1))
                    if pct - last["pct"] >= 10 or i == total:
                        last["pct"] = pct
                        loop.call_soon_threadsafe(progress_updates.put_nowait, pct)

                progress_updates: asyncio.Queue = asyncio.Queue()

                async def pump() -> None:
                    while True:
                        pct = await progress_updates.get()
                        if pct is None:
                            return
                        item.progress = pct
                        await _progress(session, project, item)

                pumper = asyncio.create_task(pump())
                try:
                    async with rt.lock:
                        await asyncio.to_thread(rt.add_knowledge, item.id, item.name, text, cb)
                finally:
                    progress_updates.put_nowait(None)
                    await pumper
                item.status, item.progress = "ready", 100
                item.indexed_at = datetime.now(timezone.utc)
            await activity.log(session, project, "KNOWLEDGE", f"indexing completed {item.name}", ref_type="knowledge", ref_id=item.id)
        except Exception as exc:
            log.exception("indexing %s failed", item_id)
            item.status, item.error = "failed", f"{type(exc).__name__}: {exc}"[:500]
            await activity.log(session, project, "KNOWLEDGE", f"indexing failed {item.name}: {item.error[:80]}", ref_type="knowledge", ref_id=item.id)
        await _progress(session, project, item)


async def delete_item(session: AsyncSession, project: Project, item: KnowledgeItem, cfg: ResolvedLlmConfig) -> None:
    if item.kind not in runtimes.STRUCTURED_KINDS:
        rt = runtimes.cached(project.id)
        if rt is None:
            try:
                rt = await runtimes.get_runtime(session, project, cfg)
            except Exception:
                rt = None
        if rt is not None:
            await asyncio.to_thread(rt.remove_knowledge, item.id)
    name, kind = item.name, item.kind
    await session.delete(item)
    await session.flush()
    await activity.log(session, project, "KNOWLEDGE", f"removed {name}", ref_type="knowledge", ref_id=item.id)
    if kind in runtimes.STRUCTURED_KINDS:
        runtimes.invalidate(project.id)
        await bus.publish(session, "system", "runtime.invalidate", {"project_id": project.id})
