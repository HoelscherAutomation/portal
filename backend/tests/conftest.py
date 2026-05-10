import asyncio

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

import app.database as db_module
from app.config import resolve_test_database_url
from app.main import app


def _ensure_test_database_exists(test_url: str) -> None:
    """Connect to the postgres admin DB and CREATE DATABASE if the test DB doesn't exist."""
    # Convert SQLAlchemy URL → asyncpg URL (drop the +asyncpg) for the bootstrap connection.
    # Also swap the target database to "postgres" (the admin DB) for the CREATE DATABASE call.
    asyncpg_url = test_url.replace("postgresql+asyncpg://", "postgresql://")
    base, _, test_dbname = asyncpg_url.rpartition("/")
    admin_url = f"{base}/postgres"

    async def _create() -> None:
        conn = await asyncpg.connect(admin_url)
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", test_dbname
            )
            if not exists:
                # CREATE DATABASE cannot run inside a transaction, and the database name can't be parameterized.
                # test_dbname comes from our own settings, not user input — safe to interpolate.
                await conn.execute(f'CREATE DATABASE "{test_dbname}"')
        finally:
            await conn.close()

    asyncio.run(_create())


@pytest.fixture(scope="session", autouse=True)
def _patch_engine():
    """Replace the module-level engine with a NullPool engine pointed at the test database.

    asyncpg connections are loop-bound. Using NullPool avoids the
    'Future attached to a different loop' error when pytest-asyncio
    creates a session-scoped event loop after import-time engine creation.

    The test database is auto-created if it doesn't exist, so the production
    database is never touched by the test suite.
    """
    test_url = resolve_test_database_url()
    _ensure_test_database_exists(test_url)

    test_engine = create_async_engine(
        test_url,
        echo=False,
        future=True,
        poolclass=NullPool,
    )
    test_session_maker = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    db_module.engine = test_engine
    db_module.async_session_maker = test_session_maker
    yield
    # No explicit dispose needed — NullPool closes connections immediately


@pytest.fixture(scope="session", autouse=True)
def _migrate(_patch_engine):
    """Apply alembic migrations once per test session, against the test database."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", resolve_test_database_url())
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def _truncate_users():
    """Reset users table between tests."""
    async with db_module.async_session_maker() as session:
        await session.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))
        await session.commit()


@pytest.fixture(autouse=True)
async def _reset_tenant():
    """Reset tenant_config row 1 to defaults between tests."""
    async with db_module.async_session_maker() as session:
        await session.execute(
            text(
                "UPDATE tenant_config SET "
                "company_name = 'My Company', "
                "primary_color = '#6dd5fa', "
                "logo_filename = NULL, "
                "welcome_message = NULL "
                "WHERE id = 1"
            )
        )
        await session.commit()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
