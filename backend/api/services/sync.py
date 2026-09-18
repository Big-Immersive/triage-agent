"""Sync scheduler: polls pull-based integrations on their interval. Any replica
may run a sync; the claim is an UPDATE on the integration row (next_sync_at
reached, lock free or stale), so two replicas never poll the same source.
Pulled items go through the shared task ingestion (tasks + auto-run) or, for
knowledge-type items, through the knowledge service."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, text, update

from ..core.bus import REPLICA_ID, bus
from ..core.config import settings
from ..core.db import SessionLocal
from ..integrations.adapters import _plain
from ..integrations.catalog import CATALOG
from ..integrations.pollers import INTERVALS, POLLERS
from ..models import Integration, KnowledgeItem, Project, now
from . import activity, knowledge
from . import tasks as task_service

log = logging.getLogger("triage.sync")
LOCK_STALE_S = 600


class SyncScheduler:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.CancelledError, Exception):
                pass

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                claimed = await self._claim()
                if claimed:
                    await self.run_sync(claimed)
                    continue
            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("sync loop error")
            await asyncio.sleep(settings.SYNC_POLL_S)

    async def _claim(self) -> Optional[str]:
        async with SessionLocal() as s:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=LOCK_STALE_S)
            row = (await s.execute(text(
                "UPDATE integrations SET sync_locked_by = :me, sync_locked_at = now() WHERE id = ("
                "  SELECT id FROM integrations WHERE status IN ('connected','error') AND next_sync_at IS NOT NULL AND next_sync_at <= now()"
                "  AND (sync_locked_at IS NULL OR sync_locked_at < :cutoff) ORDER BY next_sync_at LIMIT 1 FOR UPDATE SKIP LOCKED"
                ") RETURNING id"), {"me": REPLICA_ID, "cutoff": cutoff})).first()
            await s.commit()
            return row[0] if row else None

    async def run_sync(self, integration_id: str, *, manual: bool = False) -> str:
        async with SessionLocal() as s:
            row = await s.get(Integration, integration_id)
            if row is None:
                return "gone"
            project = await s.get(Project, row.project_id)
            poller = POLLERS.get(row.provider)
            note = "no poller"
            try:
                if poller is None:
                    note = "push-only provider"
                else:
                    cfg = _plain(row.config or {})
                    items, cursor, note = await poller(cfg, dict(row.sync_cursor or {}))
                    tasks_in = [i for i in items if i.get("kind") != "knowledge"]
                    know_in = [i for i in items if i.get("kind") == "knowledge"]
                    if tasks_in:
                        res = await task_service.ingest(s, project, tasks_in, source=row.provider, log_as=row.provider.upper())
                        note += f" → {len(res['created'])} task(s)"
                        row.inbound_count = (row.inbound_count or 0) + len(res["created"])
                    for k in know_in:
                        await self._upsert_knowledge(s, project, k)
                    row.sync_cursor = cursor
                    if row.status == "error":
                        row.status = "connected"
                if note.startswith("error"):
                    row.status = "error"
                row.last_sync_result = note[:500]
            except Exception as exc:
                note = f"error: {type(exc).__name__}: {str(exc)[:200]}"
                row.status = "error"
                row.last_sync_result = note
                await activity.log(s, project, "SYSTEM", f"{row.provider.upper()} sync failed: {note}", ref_type="integration", ref_id=row.provider)
            row.last_sync_at = now()
            row.next_sync_at = now() + timedelta(seconds=INTERVALS.get(row.provider, 300))
            row.sync_locked_by, row.sync_locked_at = None, None
            await bus.publish_project(s, project.id, project.owner_id, "integration.synced", {"provider": row.provider, "result": note, "at": row.last_sync_at})
            await s.commit()
            return note

    async def _upsert_knowledge(self, s, project: Project, k: dict) -> None:
        existing = (await s.execute(select(KnowledgeItem).where(KnowledgeItem.project_id == project.id, KnowledgeItem.name == k["name"]))).scalar_one_or_none()
        if existing is not None:
            from ..models import File
            from . import storage
            frow = await s.get(File, existing.file_id) if existing.file_id else None
            if frow is not None:
                await storage.write_file(s, project, frow.path, k["data"])
                existing.size_bytes = len(k["data"])
                existing.status, existing.progress, existing.error = "indexing", 0, None
                await s.commit()
                knowledge.schedule_index(project.id, existing.id)
                return
        item = await knowledge.create_item(s, project, name=k["name"], data=k["data"], kind=k.get("type") or "auto", folder="/uploads/synced")
        await s.commit()
        knowledge.schedule_index(project.id, item.id)


sync_scheduler = SyncScheduler()


def schedule_first_sync(row: Integration) -> None:
    """Called when an integration is connected: pull providers get polled soon."""
    if row.provider in POLLERS and CATALOG[row.provider]["inbound"]["mode"] in ("poll", "both"):
        row.next_sync_at = now() + timedelta(seconds=5)
    else:
        row.next_sync_at = None
