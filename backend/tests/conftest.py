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
from app.config import get_settings
from app.database import async_session_maker
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _patch_engine():
    """Replace the module-level engine with a NullPool engine for tests.

    asyncpg connections are loop-bound. Using NullPool avoids the
    'Future attached to a different loop' error when pytest-asyncio
    creates a session-scoped event loop after import-time engine creation.
    """
    test_engine = create_async_engine(
        get_settings().database_url,
        echo=False,
        future=True,
        poolclass=NullPool,
    )
    test_session_maker = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    # Patch module-level objects so all code paths use the NullPool engine
    db_module.engine = test_engine
    db_module.async_session_maker = test_session_maker
    yield
    # No explicit dispose needed — NullPool closes connections immediately


@pytest.fixture(scope="session", autouse=True)
def _migrate(_patch_engine):
    """Apply alembic migrations once per test session."""
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def _truncate_users():
    """Reset users table between tests."""
    async with db_module.async_session_maker() as session:
        await session.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))
        await session.commit()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
