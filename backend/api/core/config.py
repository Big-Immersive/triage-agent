from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent.parent   # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://triage:triage@localhost:5432/triage"
    TRIAGE_SECRET_KEY: str = "dev-only-change-me"           # JWT signing + Fernet key derivation
    TRIAGE_DATA_DIR: Path = ROOT / "data"
    JWT_TTL_HOURS: int = 24 * 14
    COOKIE_NAME: str = "triage_session"
    COOKIE_SECURE: bool = False
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"   # comma-separated
    APP_URL: str = "http://localhost:5173"                                # public UI url, used in notification links
    API_PUBLIC_URL: str = "http://localhost:8000"                         # public API url, used for inbound webhook URLs
    OLLAMA_HOST: str = "http://localhost:11434"
    OPENROUTER_PRICING_TTL_S: int = 6 * 3600
    SERVE_STATIC: bool = False           # optional: serve web/dist from FastAPI (single-service mode)
    PORT: int = 8000
    # Storage: "local" (dev) or "s3" (any S3-compatible bucket: AWS, R2, B2, MinIO) for multi-replica deploys.
    STORAGE_BACKEND: str = "local"
    S3_BUCKET: str = ""
    S3_ENDPOINT_URL: str = ""
    S3_REGION: str = "auto"
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    # Run workers per replica and queue polling.
    RUN_WORKERS: int = 4
    RUN_POLL_S: float = 1.0
    RUN_HEARTBEAT_S: int = 15
    RUN_STALE_S: int = 90
    SYNC_POLL_S: float = 10.0            # how often a replica looks for due integration syncs
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    @property
    def cors_origins(self) -> list[str]:
        # Railway env vars are plain strings: CORS_ORIGINS=https://ui.up.railway.app,https://app.example.com
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _asyncpg_url(cls, v: str) -> str:
        # Railway / Heroku hand out postgres:// or postgresql://; SQLAlchemy needs the async driver.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+asyncpg://" + v[len(prefix):]
        return v

    @property
    def projects_dir(self) -> Path:
        return self.TRIAGE_DATA_DIR / "projects"


settings = Settings()
