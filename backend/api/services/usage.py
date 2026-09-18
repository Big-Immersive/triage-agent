"""LLM usage accounting: token counts per (run, agent, model) priced from
OpenRouter's public model list (cached). Ollama is free. Counts come from
LlamaIndex's TokenCountingHandler, so they are estimates — flagged as such."""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models import LlmUsage, Project, Run
from .llm import RunLlmFactory

log = logging.getLogger("triage.usage")

_pricing: dict[str, tuple[float, float]] = {}   # model id -> ($/prompt token, $/completion token)
_pricing_at: float = 0.0


async def pricing() -> dict[str, tuple[float, float]]:
    global _pricing, _pricing_at
    if _pricing and time.time() - _pricing_at < settings.OPENROUTER_PRICING_TTL_S:
        return _pricing
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://openrouter.ai/api/v1/models")
            r.raise_for_status()
        table = {}
        for m in r.json().get("data", []):
            p = m.get("pricing") or {}
            try:
                table[m["id"]] = (float(p.get("prompt", 0) or 0), float(p.get("completion", 0) or 0))
            except (TypeError, ValueError):
                continue
        if table:
            _pricing, _pricing_at = table, time.time()
    except Exception as exc:  # offline: keep whatever we had
        log.warning("pricing fetch failed: %s", exc)
    return _pricing


def cost_for(provider: str, model: str, prompt: int, completion: int, table: dict) -> tuple[float, bool]:
    if provider != "openrouter":
        return 0.0, False
    rates = table.get(model)
    if not rates:
        return 0.0, True
    return prompt * rates[0] + completion * rates[1], True


async def record_run_usage(session: AsyncSession, project: Project, run: Run, factory: RunLlmFactory) -> None:
    table = await pricing()
    for agent_name, c in factory.counters.items():
        h = c.handler
        if h.total_llm_token_count == 0 and not h.llm_token_counts:
            continue
        cost, estimated = cost_for(c.provider, c.model, h.prompt_llm_token_count, h.completion_llm_token_count, table)
        session.add(LlmUsage(
            user_id=project.owner_id, project_id=project.id, run_id=run.id, agent_name=agent_name,
            provider=c.provider, model=c.model,
            prompt_tokens=h.prompt_llm_token_count, completion_tokens=h.completion_llm_token_count,
            llm_calls=len(h.llm_token_counts), cost_usd=cost, estimated=estimated,
        ))
    await session.flush()


async def summary_for_user(session: AsyncSession, user_id: str) -> dict:
    per_project = (await session.execute(
        select(
            LlmUsage.project_id, Project.name, Project.slug,
            func.sum(LlmUsage.prompt_tokens), func.sum(LlmUsage.completion_tokens),
            func.sum(LlmUsage.cost_usd), func.count(func.distinct(LlmUsage.run_id)), func.sum(LlmUsage.llm_calls),
        )
        .join(Project, Project.id == LlmUsage.project_id)
        .where(LlmUsage.user_id == user_id)
        .group_by(LlmUsage.project_id, Project.name, Project.slug)
        .order_by(func.sum(LlmUsage.cost_usd).desc())
    )).all()
    per_model = (await session.execute(
        select(LlmUsage.provider, LlmUsage.model, func.sum(LlmUsage.prompt_tokens), func.sum(LlmUsage.completion_tokens), func.sum(LlmUsage.cost_usd), func.sum(LlmUsage.llm_calls))
        .where(LlmUsage.user_id == user_id)
        .group_by(LlmUsage.provider, LlmUsage.model)
        .order_by(func.sum(LlmUsage.cost_usd).desc())
    )).all()
    recent = (await session.execute(
        select(LlmUsage, Project.slug).join(Project, Project.id == LlmUsage.project_id)
        .where(LlmUsage.user_id == user_id).order_by(LlmUsage.ts.desc()).limit(50)
    )).all()
    total_cost = sum(r[5] or 0 for r in per_project)
    return {
        "total_cost_usd": total_cost,
        "total_prompt_tokens": sum(r[3] or 0 for r in per_project),
        "total_completion_tokens": sum(r[4] or 0 for r in per_project),
        "projects": [
            {"project_id": r[0], "name": r[1], "slug": r[2], "prompt_tokens": r[3] or 0, "completion_tokens": r[4] or 0,
             "cost_usd": r[5] or 0, "runs": r[6] or 0, "llm_calls": r[7] or 0}
            for r in per_project
        ],
        "models": [
            {"provider": r[0], "model": r[1], "prompt_tokens": r[2] or 0, "completion_tokens": r[3] or 0, "cost_usd": r[4] or 0, "llm_calls": r[5] or 0}
            for r in per_model
        ],
        "recent": [
            {"id": u.id, "ts": u.ts, "project_id": u.project_id, "project_slug": slug, "run_id": u.run_id, "agent_name": u.agent_name,
             "provider": u.provider, "model": u.model, "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens,
             "cost_usd": u.cost_usd, "estimated": u.estimated}
            for u, slug in recent
        ],
    }
