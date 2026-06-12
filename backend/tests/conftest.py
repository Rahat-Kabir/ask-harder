"""Test setup: point the app at askharder_test BEFORE any app import.

app.config reads DATABASE_URL at import time, and real env vars beat the
.env file — so rewriting os.environ here, first, makes every app module
(engine, alembic env, routes) hit the test database for the whole run.
"""

import asyncio
import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

_dev_url = (
    os.environ.get("DATABASE_URL") or dotenv_values(REPO_ROOT / ".env")["DATABASE_URL"]
)
TEST_DB_NAME = "askharder_test"
TEST_URL = make_url(_dev_url).set(database=TEST_DB_NAME)
os.environ["DATABASE_URL"] = TEST_URL.render_as_string(hide_password=False)
os.environ["LLM_BACKEND"] = "mock"

# app imports must come after the env rewrite above
import asyncpg  # noqa: E402
import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.auth.rate_limit import clear_all as clear_rate_limits  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.interviews.events import interview_events  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


async def _ensure_test_database() -> None:
    conn = await asyncpg.connect(
        user=TEST_URL.username,
        password=TEST_URL.password,
        host=TEST_URL.host,
        port=TEST_URL.port,
        database="postgres",
    )
    try:
        exists = await conn.fetchval(
            "select 1 from pg_database where datname = $1", TEST_DB_NAME
        )
        if not exists:
            await conn.execute(f'create database "{TEST_DB_NAME}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    """Create askharder_test if missing and bring it to the latest migration."""
    asyncio.run(_ensure_test_database())
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(autouse=True)
def clear_interview_event_bus(monkeypatch):
    import app.interviews.router as interviews_router

    monkeypatch.setattr(interviews_router, "KEEPALIVE_SECONDS", 0.05)
    monkeypatch.setattr(interviews_router, "MAX_IDLE_POLLS", 3)
    interview_events.clear()
    yield
    interview_events.clear()


@pytest.fixture(autouse=True)
def reset_rate_limits():
    # limiters are process-level singletons; without this, registrations
    # across the suite would trip the per-IP limit
    clear_rate_limits()
    yield
    clear_rate_limits()


@pytest.fixture()
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    # wipe data so tests stay independent; CASCADE clears dependent rows
    table_names = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {table_names} CASCADE"))
    # anyio gives every test a fresh event loop; pooled asyncpg connections
    # are bound to the old loop and would break the next test
    await engine.dispose()
