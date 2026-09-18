"""Configuration. LLM via OpenRouter or local Ollama; embeddings always local (Ollama).

`make_llm` / `make_embed` build model objects from explicit values — the server
calls them with each user's stored settings. `configure()` is the CLI path: it
reads the environment and sets the LlamaIndex globals.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from llama_index.core import Settings
from llama_index.core.callbacks import CallbackManager
from llama_index.core.llms import LLM
from llama_index.embeddings.ollama import OllamaEmbedding

PROJECT_ROOT = Path(__file__).resolve().parent.parent          # backend/
# The backend .env wins over a stale shell variable.
load_dotenv(PROJECT_ROOT / ".env", override=True)
SAMPLES_DIR = PROJECT_ROOT / "samples" / "orbit_run"           # the demo dataset (tracker, crash log, releases, CODEOWNERS, inbox, eval)
INBOX_DIR = SAMPLES_DIR / "inbox"
FIXTURES_DIR = SAMPLES_DIR
OUT_DIR = PROJECT_ROOT / "out"
EVAL_FILE = SAMPLES_DIR / "expected.json"

# ---- LLM provider ----------------------------------------------------------
# "openrouter" (default when OPENROUTER_API_KEY is set) or "ollama" for fully local.
#   TRIAGE_PROVIDER=ollama TRIAGE_LLM=qwen2.5:7b triage eval      # local comparison run
#   TRIAGE_LLM=z-ai/glm-5.3 triage eval                           # another OpenRouter model
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
PROVIDER = os.environ.get("TRIAGE_PROVIDER", "openrouter" if OPENROUTER_API_KEY else "ollama")
DEFAULT_MODELS = {"openrouter": "z-ai/glm-5", "ollama": "qwen2.5:7b"}
LLM_MODEL = os.environ.get("TRIAGE_LLM", DEFAULT_MODELS[PROVIDER])

# Embeddings stay local: OpenRouter serves no embedding models.
EMBED_MODEL = os.environ.get("TRIAGE_EMBED", "nomic-embed-text")
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Human gate: anything at/above this severity, or below this confidence,
# pauses for approval before a ticket is written.
GATE_SEVERITIES = {"high", "critical"}
GATE_MIN_CONFIDENCE = 0.7

# Investigator: a candidate is a duplicate only above this similarity.
DUPLICATE_MIN_SCORE = 0.65


def make_llm(
    provider: str,
    model: Optional[str] = None,
    *,
    api_key: Optional[str] = None,
    ollama_url: Optional[str] = None,
    callback_manager: Optional[CallbackManager] = None,
) -> LLM:
    model = model or DEFAULT_MODELS[provider]
    if provider == "openrouter":
        if not api_key:
            raise ValueError("OpenRouter API key is not set.")
        from llama_index.llms.openrouter import OpenRouter

        return OpenRouter(
            model=model,
            api_key=api_key,
            temperature=0.0,
            max_tokens=2048,
            context_window=128_000,
            is_function_calling_model=True,
            callback_manager=callback_manager,
            # Shows up in the OpenRouter dashboard so the spend is attributable.
            default_headers={"HTTP-Referer": "https://github.com/bim/bug-triage-agents", "X-Title": "bug-triage-agents"},
        )
    if provider == "ollama":
        from llama_index.llms.ollama import Ollama

        return Ollama(
            model=model,
            base_url=ollama_url or OLLAMA_URL,
            temperature=0.0,
            request_timeout=300.0,
            context_window=16384,
            is_function_calling_model=True,
            callback_manager=callback_manager,
        )
    raise ValueError(f"Unknown provider {provider!r}")


def make_embed(
    model: Optional[str] = None,
    ollama_url: Optional[str] = None,
    *,
    provider: str = "ollama",
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
):
    """Embeddings: local Ollama, or any OpenAI-compatible /v1/embeddings endpoint
    (OpenAI, Together, Voyage-compatible proxies...) for hosted deployments."""
    if provider == "openai_compatible":
        from llama_index.embeddings.openai import OpenAIEmbedding

        if not api_key:
            raise ValueError("Embedding API key is not set.")
        return OpenAIEmbedding(model_name=model or "text-embedding-3-small", api_base=base_url or "https://api.openai.com/v1", api_key=api_key, embed_batch_size=64)
    return OllamaEmbedding(model_name=model or EMBED_MODEL, base_url=ollama_url or OLLAMA_URL)


def configure() -> None:
    """CLI path: environment -> LlamaIndex globals."""
    if PROVIDER == "openrouter" and not OPENROUTER_API_KEY:
        raise SystemExit("OPENROUTER_API_KEY is not set (or use TRIAGE_PROVIDER=ollama).")
    Settings.llm = make_llm(PROVIDER, LLM_MODEL, api_key=OPENROUTER_API_KEY)
    Settings.embed_model = make_embed()
