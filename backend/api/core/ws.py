"""WebSocket hub: local fan-out of bus events to connected clients.

A client subscribes to project ids it owns, or to "global" (its per-user
headline channel). Delivery comes from the Postgres bus, so an event
published by any replica reaches clients on every replica."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import WebSocket

from .bus import bus


def _default(o: Any):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


class Hub:
    def __init__(self) -> None:
        self._subs: dict[str, set[WebSocket]] = defaultdict(set)
        self._owner: dict[WebSocket, str] = {}
        self._lock = asyncio.Lock()
        bus.on(self.deliver)

    @property
    def client_count(self) -> int:
        return len(self._owner)

    async def connect(self, ws: WebSocket, user_id: str) -> None:
        await ws.accept()
        async with self._lock:
            self._owner[ws] = user_id
            self._subs[f"global:{user_id}"].add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._owner.pop(ws, None)
            for socks in self._subs.values():
                socks.discard(ws)

    async def subscribe(self, ws: WebSocket, channel: str) -> None:
        async with self._lock:
            self._subs[channel].add(ws)

    async def unsubscribe(self, ws: WebSocket, channel: str) -> None:
        async with self._lock:
            self._subs[channel].discard(ws)

    async def deliver(self, channel: str, type_: str, payload: dict) -> None:
        async with self._lock:
            targets = list(self._subs.get(channel, ()))
        if not targets:
            return
        msg = json.dumps({"type": type_, "channel": channel, "payload": payload}, default=_default)
        dead = []
        for ws in targets:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


hub = Hub()
