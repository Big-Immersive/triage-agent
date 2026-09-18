"""Server tests run against the `triage_test` database with a scripted fake LLM.

Set TRIAGE_TEST_DATABASE_URL to point elsewhere. Tables are created from the
models (no Alembic) and truncated between tests.
"""

import asyncio
import os

os.environ["DATABASE_URL"] = os.environ.get("TRIAGE_TEST_DATABASE_URL", "postgresql+asyncpg://triage:triage@localhost:5432/triage_test")
os.environ["TRIAGE_SECRET_KEY"] = "test-secret-key-with-at-least-32-bytes!!"
os.environ["RUN_POLL_S"] = "0.2"
os.environ["RUN_HEARTBEAT_S"] = "1"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api import models  # noqa: F401
from api.main import app
from api.core.db import Base, engine
from api.core.config import settings

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema():
    settings.TRIAGE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)     # schema follows the models, not migrations
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture(autouse=True)
async def _clean():
    from api.routers import auth as auth_router
    auth_router._attempts.clear()   # per-IP login limiter would trip across tests
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE users, projects CASCADE"))
        tables = (await conn.execute(text("SELECT tablename FROM pg_tables WHERE tablename LIKE 'data_vectors_%'"))).scalars().all()
        for t in tables:
            await conn.execute(text(f"TRUNCATE {t}"))
    yield


@pytest_asyncio.fixture
async def client():
    """App client with lifespan running (bus listener + run workers)."""
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


async def register(client: AsyncClient, email: str, password: str = "password123") -> dict:
    r = await client.post("/api/auth/register", json={"email": email, "password": password, "name": email.split("@")[0]})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
