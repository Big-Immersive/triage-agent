"""Per-user LLM settings (key stored encrypted, returned masked) and usage."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from triage import settings as engine_settings

from ..core.deps import CurrentUser, Session
from ..models import UserSettings, now
from ..schemas import LlmSettingsIn, LlmSettingsOut
from ..core.security import decrypt, encrypt, mask
from ..services import usage
from ..services.llm import ResolvedLlmConfig

router = APIRouter(prefix="/api/me", tags=["me"])


async def _settings(session, user) -> UserSettings:
    us = await session.get(UserSettings, user.id)
    if us is None:
        us = UserSettings(user_id=user.id)
        session.add(us)
        await session.flush()
    return us


def _out(us: UserSettings) -> LlmSettingsOut:
    key = decrypt(us.openrouter_key_enc) if us.openrouter_key_enc else None
    ekey = decrypt(us.embed_api_key_enc) if us.embed_api_key_enc else None
    return LlmSettingsOut(
        provider=us.provider, openrouter_key_masked=mask(key), has_openrouter_key=bool(key),
        ollama_url=us.ollama_url, default_model=us.default_model or engine_settings.DEFAULT_MODELS[us.provider],
        embed_provider=us.embed_provider, embed_model=us.embed_model, embed_base_url=us.embed_base_url,
        embed_api_key_masked=mask(ekey), has_embed_api_key=bool(ekey), updated_at=us.updated_at,
    )


@router.get("/llm", response_model=LlmSettingsOut)
async def get_llm(user: CurrentUser, session: Session):
    return _out(await _settings(session, user))


@router.put("/llm", response_model=LlmSettingsOut)
async def put_llm(body: LlmSettingsIn, user: CurrentUser, session: Session):
    us = await _settings(session, user)
    us.provider = body.provider
    if body.openrouter_key is not None:
        us.openrouter_key_enc = encrypt(body.openrouter_key.strip()) if body.openrouter_key.strip() else None
    if body.ollama_url is not None:
        us.ollama_url = body.ollama_url.strip() or engine_settings.OLLAMA_URL
    if body.default_model is not None:
        us.default_model = body.default_model.strip() or None
    if body.embed_provider is not None:
        us.embed_provider = body.embed_provider
    if body.embed_model is not None:
        us.embed_model = body.embed_model.strip() or ("nomic-embed-text" if us.embed_provider == "ollama" else "text-embedding-3-small")
    if body.embed_base_url is not None:
        us.embed_base_url = body.embed_base_url.strip() or None
    if body.embed_api_key is not None:
        us.embed_api_key_enc = encrypt(body.embed_api_key.strip()) if body.embed_api_key.strip() else None
    us.updated_at = now()
    await session.commit()
    return _out(us)


@router.post("/llm/test")
async def test_llm(user: CurrentUser, session: Session):
    cfg = ResolvedLlmConfig.from_settings(await _settings(session, user))
    checks = {}
    if cfg.provider == "ollama" or cfg.embed_provider == "ollama":
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"{cfg.ollama_url}/api/tags")
                models = [m["name"] for m in r.json().get("models", [])]
                checks["ollama"] = {"ok": True, "models": models, "embed_present": cfg.embed_provider != "ollama" or any(m.startswith(cfg.embed_model) for m in models)}
        except Exception as exc:
            checks["ollama"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if cfg.embed_provider == "openai_compatible":
        try:
            from ..services.llm import make_embed
            emb = make_embed(cfg)
            vec = await emb.aget_query_embedding("ping")
            checks["embeddings"] = {"ok": True, "dimensions": len(vec), "model": cfg.embed_model}
        except Exception as exc:
            checks["embeddings"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    if cfg.provider == "openrouter":
        if not cfg.api_key:
            checks["openrouter"] = {"ok": False, "error": "no key saved"}
        else:
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await c.get("https://openrouter.ai/api/v1/auth/key", headers={"Authorization": f"Bearer {cfg.api_key}"})
                    if r.status_code == 200:
                        d = r.json().get("data", {})
                        checks["openrouter"] = {"ok": True, "label": d.get("label"), "usage": d.get("usage"), "limit": d.get("limit")}
                    else:
                        checks["openrouter"] = {"ok": False, "error": f"HTTP {r.status_code}"}
            except Exception as exc:
                checks["openrouter"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    ok = all(v.get("ok") for v in checks.values()) and checks.get("ollama", {}).get("embed_present", True)
    return {"ok": ok, "provider": cfg.provider, "default_model": cfg.default_model, "embed_provider": cfg.embed_provider, "checks": checks}


@router.get("/usage")
async def get_usage(user: CurrentUser, session: Session):
    return await usage.summary_for_user(session, user.id)
