"""Build and cache the engine's ProjectRuntime for a project.

Vectors live in Postgres (pgvector) in one table per embedding dimension;
nodes are tagged with project_id + kind and every search filters on both.
The runtime object itself is a per-process cache of the project's tracker
tickets / crash log / ownership / releases, rebuilt when the project's
structured knowledge changes (the bus tells every replica to drop it)."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from triage import runtime as engine_runtime
from triage.runtime import ProjectRuntime

from ..core.config import settings
from ..core.db import SessionLocal
from ..models import File, KnowledgeItem, Project, TicketCounter
from . import storage
from .llm import ResolvedLlmConfig, make_embed

log = logging.getLogger("triage.runtimes")
STRUCTURED_KINDS = ("tracker", "crashlog", "releases", "codeowners")

_stores: dict[int, object] = {}
_stores_lock = threading.Lock()
_dims: dict[tuple, int] = {}
_build_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)   # per project, per process


def _pg_params() -> dict:
    u = urlparse(settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"))
    return {"host": u.hostname, "port": u.port or 5432, "database": u.path.lstrip("/"), "user": u.username or "", "password": u.password or ""}


async def embed_dim(cfg: ResolvedLlmConfig, embed) -> int:
    key = (cfg.embed_provider, cfg.embed_model, cfg.embed_base_url or cfg.ollama_url)
    if key not in _dims:
        vec = await embed.aget_query_embedding("dimension probe")
        _dims[key] = len(vec)
    return _dims[key]


def _make_store(dim: int):
    """One pgvector table per embedding size (a table has a fixed dimension). Setup runs once per process."""
    with _stores_lock:
        if dim not in _stores:
            from llama_index.vector_stores.postgres import PGVectorStore

            store = PGVectorStore.from_params(
                **_pg_params(), table_name=f"vectors_{dim}", embed_dim=dim, use_jsonb=True,
                indexed_metadata_keys=[("project_id", "text"), ("kind", "text")],
                hnsw_kwargs={"hnsw_m": 16, "hnsw_ef_construction": 64, "hnsw_ef_search": 40, "hnsw_dist_method": "vector_cosine_ops"},
            )
            store._initialize()
            _stores[dim] = store
        return _stores[dim]


async def vector_store(dim: int):
    return await asyncio.to_thread(_make_store, dim)


async def _read_item(session: AsyncSession, project: Project, item: KnowledgeItem) -> str:
    if not item.file_id:
        return ""
    row = await session.get(File, item.file_id)
    if row is None or row.project_id != project.id:
        return ""
    return (await storage.read_bytes(row)).decode("utf-8", errors="replace")


async def load_sources(session: AsyncSession, project: Project) -> dict:
    items = (await session.execute(
        select(KnowledgeItem).where(KnowledgeItem.project_id == project.id, KnowledgeItem.kind.in_(STRUCTURED_KINDS), KnowledgeItem.status == "ready")
        .order_by(KnowledgeItem.created_at)
    )).scalars().all()
    src = {"tickets": [], "crashes_csv": "", "codeowners": "", "releases": {}}
    for it in items:
        txt = await _read_item(session, project, it)
        if not txt:
            continue
        try:
            if it.kind == "tracker":
                data = json.loads(txt)
                src["tickets"].extend(data if isinstance(data, list) else data.get("tickets", []))
            elif it.kind == "crashlog":
                src["crashes_csv"] = txt if not src["crashes_csv"] else src["crashes_csv"] + "\n" + "\n".join(txt.splitlines()[1:])
            elif it.kind == "codeowners":
                src["codeowners"] += "\n" + txt
            elif it.kind == "releases":
                src["releases"] = json.loads(txt)
        except Exception as exc:
            log.warning("knowledge item %s unreadable: %s", it.id, exc)
    # Tickets the agents created earlier live as /out/tickets/*.json artifacts.
    created = (await session.execute(select(File).where(File.project_id == project.id, File.path.like("/out/tickets/%.json")))).scalars().all()
    for f in created:
        try:
            t = json.loads((await storage.read_bytes(f)).decode("utf-8"))
            src["tickets"].append({"id": t["id"], "title": t["title"], "status": "open", "severity": t.get("severity"), "component": t.get("component"),
                                   "affected_versions": t.get("affected_versions", []), "fixed_in": None, "owner": t.get("owner"), "description": t.get("actual", "")})
        except Exception:
            continue
    return src


def _allocator(project_id: str):
    async def allocate() -> str:
        async with SessionLocal() as s:
            row = (await s.execute(
                text("UPDATE ticket_counters SET next_num = next_num + 1 WHERE project_id = :pid RETURNING prefix, next_num - 1"),
                {"pid": project_id},
            )).first()
            if row is None:
                await s.execute(text("INSERT INTO ticket_counters (project_id, prefix, next_num) VALUES (:pid, 'OR', 102) ON CONFLICT DO NOTHING"), {"pid": project_id})
                await s.commit()
                return await allocate()
            await s.commit()
            return f"{row[0]}-{row[1]}"
    return allocate


async def ensure_counter(session: AsyncSession, project_id: str, prefix: str, next_num: int) -> None:
    """Counter starts above every known ticket id; never moves backwards (upsert: replica-safe)."""
    await session.execute(
        text("INSERT INTO ticket_counters (project_id, prefix, next_num) VALUES (:pid, :prefix, :n) "
             "ON CONFLICT (project_id) DO UPDATE SET prefix = EXCLUDED.prefix, next_num = GREATEST(ticket_counters.next_num, EXCLUDED.next_num)"),
        {"pid": project_id, "prefix": prefix, "n": next_num},
    )


async def get_runtime(session: AsyncSession, project: Project, cfg: ResolvedLlmConfig, *, rebuild: bool = False, reindex_tickets: bool = False) -> ProjectRuntime:
    if not rebuild and not reindex_tickets:
        try:
            return engine_runtime.get(project.id)
        except RuntimeError:
            pass
    async with _build_locks[project.id]:
        if not rebuild and not reindex_tickets:
            try:
                return engine_runtime.get(project.id)   # built while we waited
            except RuntimeError:
                pass
        src = await load_sources(session, project)
        embed = make_embed(cfg)
        dim = await embed_dim(cfg, embed)
        store = await vector_store(dim)

        def build() -> ProjectRuntime:
            return ProjectRuntime.from_sources(
                project.id, embed, tickets=src["tickets"], crashes_csv=src["crashes_csv"], codeowners=src["codeowners"], releases=src["releases"],
                vector_store=store, id_allocator=_allocator(project.id), index_tickets=False,
            )

        rt = await asyncio.to_thread(build)
        # Embed the tracker only when it changed (or was never embedded); other replicas reuse the vectors.
        # The advisory lock stops two replicas from embedding the same tracker at once.
        if src["tickets"] and (reindex_tickets or not await asyncio.to_thread(rt.has_ticket_vectors)):
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"tickets:{project.id}"})
            if reindex_tickets or not await asyncio.to_thread(rt.has_ticket_vectors):
                await asyncio.to_thread(rt.rebuild_tickets)
        await ensure_counter(session, project.id, rt.ticket_prefix, rt.next_ticket_num)
        await session.commit()
        return engine_runtime.register(rt)


def invalidate(project_id: str) -> None:
    engine_runtime.unregister(project_id)


def cached(project_id: str) -> Optional[ProjectRuntime]:
    try:
        return engine_runtime.get(project_id)
    except RuntimeError:
        return None


async def purge_vectors(project_id: str) -> None:
    """Project deleted: drop its nodes from every vector table."""
    async with SessionLocal() as s:
        tables = (await s.execute(text("SELECT tablename FROM pg_tables WHERE tablename LIKE 'data_vectors_%'"))).scalars().all()
        for t in tables:
            await s.execute(text(f"DELETE FROM {t} WHERE metadata_->>'project_id' = :pid"), {"pid": project_id})
        await s.commit()
