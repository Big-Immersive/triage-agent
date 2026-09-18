"""Cross-replica event bus on Postgres LISTEN/NOTIFY.

Every API replica LISTENs on one channel; `publish` NOTIFYs inside the
caller's transaction so events land only after the rows they describe are
committed. Each replica hands received events to its local WebSocket hub and
to any in-process handlers (run workers waiting on approvals / cancels).

NOTIFY payloads are capped at 8000 bytes, so large fields are trimmed — the
REST API always has the full record.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings

log = logging.getLogger("triage.bus")
CHANNEL = "triage_events"
MAX_PAYLOAD = 7000
Handler = Callable[[str, str, dict], Awaitable[None]]   # (channel, type, payload)

REPLICA_ID = f"{socket.gethostname()}-{os.getpid()}"


def _default(o: Any):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


def _trim(payload: dict) -> dict:
    """Cut long strings so the message fits NOTIFY's limit; mark what was cut."""
    def cut(v, budget):
        if isinstance(v, str) and len(v) > budget:
            return v[:budget] + "…"
        if isinstance(v, dict):
            return {k: cut(x, budget) for k, x in v.items()}
        if isinstance(v, list):
            return [cut(x, budget) for x in v[:50]]
        return v
    for budget in (2000, 800, 300, 120):
        p = cut(payload, budget)
        if len(json.dumps(p, default=_default)) <= MAX_PAYLOAD:
            if budget < 2000:
                p["_trimmed"] = True
            return p
    return {"_trimmed": True, "_dropped": True}


class Bus:
    def __init__(self) -> None:
        self._conn: Optional[asyncpg.Connection] = None
        self._handlers: list[Handler] = []
        self._task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def on(self, handler: Handler) -> None:
        self._handlers.append(handler)

    def off(self, handler: Handler) -> None:
        try:
            self._handlers.remove(handler)
        except ValueError:
            pass

    # -------------------------------------------------------------- listen --
    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._listen_forever())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self._conn:
            try:
                await self._conn.close()
            except Exception:
                pass

    def _dsn(self) -> str:
        return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    async def _listen_forever(self) -> None:
        backoff = 1
        while True:
            try:
                self._conn = await asyncpg.connect(self._dsn())
                await self._conn.add_listener(CHANNEL, self._on_notify)
                log.info("bus listening as %s", REPLICA_ID)
                backoff = 1
                while True:
                    await asyncio.sleep(30)
                    await self._conn.execute("SELECT 1")   # keepalive; raises if the connection died
            except asyncio.CancelledError:
                return
            except Exception as exc:
                log.warning("bus listener lost (%s); reconnecting in %ss", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def _on_notify(self, conn, pid, channel, payload: str) -> None:
        try:
            msg = json.loads(payload)
        except json.JSONDecodeError:
            return
        asyncio.create_task(self._dispatch(msg.get("channel", ""), msg.get("type", ""), msg.get("payload") or {}))

    async def _dispatch(self, channel: str, type_: str, payload: dict) -> None:
        for h in list(self._handlers):
            try:
                await h(channel, type_, payload)
            except Exception:
                log.exception("bus handler failed")

    # ------------------------------------------------------------- publish --
    async def publish(self, session: AsyncSession, channel: str, type_: str, payload: dict | None = None) -> None:
        msg = json.dumps({"channel": channel, "type": type_, "payload": _trim(payload or {})}, default=_default)
        await session.execute(text("SELECT pg_notify(:ch, :msg)"), {"ch": CHANNEL, "msg": msg})

    async def publish_project(self, session: AsyncSession, project_id: str, owner_id: str, type_: str, payload: dict | None = None, headline: str | None = None) -> None:
        """Project channel gets the full payload; the owner's global channel gets a headline only."""
        await self.publish(session, project_id, type_, payload)
        if headline is not None:
            await self.publish(session, f"global:{owner_id}", type_, {"project_id": project_id, "headline": headline})


bus = Bus()
