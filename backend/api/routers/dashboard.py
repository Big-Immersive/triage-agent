from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from sqlalchemy import func, select, text

from triage.tools.registry import describe

from ..core.bus import REPLICA_ID
from ..core.config import settings
from ..core.deps import CurrentUser, Session
from ..models import Activity, Agent, Approval, Project, Run, UserSettings
from ..services.llm import ResolvedLlmConfig
from ..core.ws import hub

router = APIRouter(tags=["dashboard"])
ACTIVE_RUN = ("queued", "running", "waiting_approval")
ONLINE = ("thinking", "running", "tool_call", "waiting", "human_input")


@router.get("/api/dashboard")
async def dashboard(user: CurrentUser, session: Session):
    pids = (await session.execute(select(Project.id).where(Project.owner_id == user.id, Project.status != "archived"))).scalars().all()
    metrics = {
        "total_projects": len(pids),
        "active_agents": (await session.execute(select(func.count()).where(Agent.project_id.in_(pids), Agent.status.in_(ONLINE)))).scalar() if pids else 0,
        "active_runs": (await session.execute(select(func.count()).where(Run.project_id.in_(pids), Run.status.in_(ACTIVE_RUN)))).scalar() if pids else 0,
        "waiting_approvals": (await session.execute(select(func.count()).where(Approval.project_id.in_(pids), Approval.status == "pending"))).scalar() if pids else 0,
    }
    recent = (await session.execute(select(Project).where(Project.id.in_(pids)).order_by(Project.last_activity_at.desc()).limit(6))).scalars().all() if pids else []
    approvals = (await session.execute(
        select(Approval, Project.slug, Project.name).join(Project, Project.id == Approval.project_id)
        .where(Approval.project_id.in_(pids), Approval.status == "pending").order_by(Approval.requested_at.desc()).limit(20)
    )).all() if pids else []
    activity = (await session.execute(
        select(Activity, Project.slug).join(Project, Project.id == Activity.project_id).where(Activity.project_id.in_(pids)).order_by(Activity.id.desc()).limit(40)
    )).all() if pids else []
    return {
        "metrics": metrics,
        "recent_projects": [{"id": p.id, "name": p.name, "slug": p.slug, "icon": p.icon, "status": p.status, "last_activity_at": p.last_activity_at} for p in recent],
        "approval_queue": [{"id": a.id, "project_id": a.project_id, "project_slug": slug, "project_name": name, "agent_name": a.agent_name, "action": a.action,
                            "confidence": a.confidence, "run_id": a.run_id, "requested_at": a.requested_at} for a, slug, name in approvals],
        "activity": [{"id": a.id, "ts": a.ts, "category": a.category, "message": a.message, "project_id": a.project_id, "project_slug": slug} for a, slug in activity],
    }


@router.get("/api/system/health")
async def health(user: CurrentUser, session: Session):
    """What the `● SYSTEM ONLINE` indicator and SYSTEM HEALTH panel are based on."""
    checks: dict = {}
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:
        checks["database"] = {"ok": False, "error": str(exc)[:200]}
    cfg = ResolvedLlmConfig.from_settings(await session.get(UserSettings, user.id))
    if cfg.provider == "ollama" or cfg.embed_provider == "ollama":
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get(f"{cfg.ollama_url}/api/tags")
                models = [m["name"] for m in r.json().get("models", [])]
                checks["ollama"] = {"ok": True, "models": len(models), "embed_present": cfg.embed_provider != "ollama" or any(m.startswith(cfg.embed_model) for m in models)}
        except Exception as exc:
            checks["ollama"] = {"ok": False, "error": f"{type(exc).__name__}"}
    ok_llm, why = cfg.ready()
    checks["llm"] = {"ok": ok_llm, "provider": cfg.provider, "model": cfg.default_model, "note": why or None}
    checks["embeddings"] = {"ok": cfg.embed_provider != "openai_compatible" or bool(cfg.embed_api_key), "provider": cfg.embed_provider, "model": cfg.embed_model}
    online = checks["database"]["ok"] and ok_llm and checks.get("ollama", {"ok": True}).get("ok", True)
    return {
        "online": online, "replica": REPLICA_ID, "ws_clients": hub.client_count, "storage": settings.STORAGE_BACKEND,
        "run_workers": settings.RUN_WORKERS, "time": datetime.now(timezone.utc), "checks": checks,
    }


@router.get("/api/system/tools")
async def tools(user: CurrentUser):
    return describe()


@router.get("/api/system/models")
async def models(user: CurrentUser, session: Session):
    """Model suggestions for the agent editor: what OpenRouter / the user's Ollama offer."""
    cfg = ResolvedLlmConfig.from_settings(await session.get(UserSettings, user.id))
    out: dict = {"openrouter": [], "ollama": []}
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get(f"{cfg.ollama_url}/api/tags")
            out["ollama"] = [m["name"] for m in r.json().get("models", []) if "embed" not in m["name"]]
    except Exception:
        pass
    try:
        from ..services.usage import pricing
        table = await pricing()
        prefer = ("z-ai/", "anthropic/", "openai/", "google/", "qwen/", "meta-llama/", "deepseek/", "mistralai/")
        out["openrouter"] = sorted([m for m in table if m.startswith(prefer)])[:400]
    except Exception:
        pass
    return out
