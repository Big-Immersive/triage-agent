"""FastAPI application: REST API + WebSocket, background run workers, bus listener."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .core.bus import bus
from .core.config import ROOT, settings
from .core.db import SessionLocal, engine
from .models import Project
from .routers import activity, agents, approvals, auth, dashboard, files, inbound, integrations, intake, knowledge, me, memories, projects, runs, tasks, tickets
from .core.security import ws_user
from .services import knowledge as knowledge_service
from .services.runs import run_service
from .services.sync import sync_scheduler
from .core.ws import hub

logging.basicConfig(level=logging.INFO, format="%(levelname)-5s %(name)s: %(message)s")
log = logging.getLogger("triage.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.TRIAGE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    await bus.start()
    await run_service.start()
    await sync_scheduler.start()
    log.info("ready: workers=%s storage=%s", settings.RUN_WORKERS, settings.STORAGE_BACKEND)
    try:
        yield
    finally:
        await sync_scheduler.stop()
        await run_service.stop()
        await knowledge_service.wait_idle()
        await bus.stop()
        await engine.dispose()


app = FastAPI(title="triage dashboard", version="0.1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in (auth, me, projects, agents, tasks, runs, approvals, memories, knowledge, files, activity, integrations, dashboard, intake, tickets, inbound):
    app.include_router(r.router)


@app.get("/api/ping")
async def ping():
    return {"ok": True}


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    async with SessionLocal() as session:
        user = await ws_user(ws, session)
        if user is None:
            await ws.close(code=4401)
            return
        owned = set((await session.execute(select(Project.id).where(Project.owner_id == user.id))).scalars().all())
    await hub.connect(ws, user.id)
    try:
        await ws.send_text(json.dumps({"type": "hello", "channel": "system", "payload": {"user_id": user.id}}))
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if "subscribe" in msg:
                ch = str(msg["subscribe"])
                if ch == "global":
                    continue  # always subscribed to the user's own global channel
                if ch not in owned:
                    # Re-check: the project may have been created after the socket opened.
                    async with SessionLocal() as s2:
                        p = await s2.get(Project, ch)
                        if p is None or p.owner_id != user.id:
                            await ws.send_text(json.dumps({"type": "error", "channel": ch, "payload": {"error": "not found"}}))
                            continue
                        owned.add(ch)
                await hub.subscribe(ws, ch)
                await ws.send_text(json.dumps({"type": "subscribed", "channel": ch, "payload": {}}))
            elif "unsubscribe" in msg:
                await hub.unsubscribe(ws, str(msg["unsubscribe"]))
            elif msg.get("ping"):
                await ws.send_text(json.dumps({"type": "pong", "channel": "system", "payload": {}}))
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(ws)


# Optional single-service mode: serve the built UI from the API container.
_dist = ROOT.parent / "frontend" / "dist"
if settings.SERVE_STATIC and _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        target = _dist / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(_dist / "index.html")
