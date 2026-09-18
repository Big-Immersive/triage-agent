"""Build LLM / embedding objects from a user's stored settings, with per-run token counting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from llama_index.core.callbacks import CallbackManager, TokenCountingHandler
from llama_index.core.llms import LLM

from triage import settings as engine_settings

from ..models import UserSettings
from ..core.security import decrypt


@dataclass
class ResolvedLlmConfig:
    provider: str
    default_model: str
    api_key: Optional[str]
    ollama_url: str
    embed_provider: str
    embed_model: str
    embed_base_url: Optional[str]
    embed_api_key: Optional[str]

    @classmethod
    def from_settings(cls, us: Optional[UserSettings]) -> "ResolvedLlmConfig":
        provider = (us.provider if us else "openrouter") or "openrouter"
        key = decrypt(us.openrouter_key_enc) if us and us.openrouter_key_enc else None
        ekey = decrypt(us.embed_api_key_enc) if us and us.embed_api_key_enc else None
        eprov = (us.embed_provider if us else "ollama") or "ollama"
        return cls(
            provider=provider,
            default_model=(us.default_model if us and us.default_model else engine_settings.DEFAULT_MODELS[provider]),
            api_key=key,
            ollama_url=(us.ollama_url if us and us.ollama_url else engine_settings.OLLAMA_URL),
            embed_provider=eprov,
            embed_model=(us.embed_model if us and us.embed_model else ("nomic-embed-text" if eprov == "ollama" else "text-embedding-3-small")),
            embed_base_url=(us.embed_base_url if us else None),
            embed_api_key=ekey,
        )

    def ready(self) -> tuple[bool, str]:
        if self.provider == "openrouter" and not self.api_key:
            return False, "No OpenRouter API key saved. Add one under settings > llm.config."
        if self.embed_provider == "openai_compatible" and not self.embed_api_key:
            return False, "No embedding API key saved. Add one under settings > llm.config."
        return True, ""


def parse_model(spec: Optional[str], cfg: ResolvedLlmConfig) -> tuple[str, str]:
    """'openrouter:z-ai/glm-5' | 'ollama:qwen2.5:7b' | 'z-ai/glm-5' (default provider) | None."""
    if not spec:
        return cfg.provider, cfg.default_model
    for p in ("openrouter", "ollama"):
        if spec.startswith(p + ":"):
            return p, spec[len(p) + 1:]
    return cfg.provider, spec


@dataclass
class AgentCounter:
    provider: str
    model: str
    handler: TokenCountingHandler


@dataclass
class RunLlmFactory:
    """Creates one LLM per agent and keeps a token counter for each, so usage
    can be attributed to (run, agent, model)."""

    cfg: ResolvedLlmConfig
    counters: dict[str, AgentCounter] = field(default_factory=dict)

    def for_agent(self, agent_name: str, model_spec: Optional[str]) -> LLM:
        provider, model = parse_model(model_spec, self.cfg)
        handler = TokenCountingHandler()
        self.counters[agent_name] = AgentCounter(provider, model, handler)
        return engine_settings.make_llm(
            provider, model, api_key=self.cfg.api_key, ollama_url=self.cfg.ollama_url,
            callback_manager=CallbackManager([handler]),
        )


def make_embed(cfg: ResolvedLlmConfig):
    return engine_settings.make_embed(cfg.embed_model, cfg.ollama_url, provider=cfg.embed_provider, base_url=cfg.embed_base_url, api_key=cfg.embed_api_key)
