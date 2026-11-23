from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.database as db_module


async def test_health_returns_ok_with_no_internal_state(client):
    """Public liveness probe — must NOT leak internal state to unauth callers."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok"}  # exactly this; no phone_home leak


async def test_health_internal_requires_auth(client):
    """The /internal variant exposes phone-home state and must be auth-gated."""
    response = await client.get("/api/health/internal")
    assert response.status_code == 401


async def test_health_returns_503_when_database_unreachable(client, monkeypatch):
    """A real engine pointed at a closed port: the probe must say 503, not 200 or 500."""
    dead_engine = create_async_engine(
        "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nowhere", poolclass=NullPool
    )
    monkeypatch.setattr(
        db_module,
        "async_session_maker",
        async_sessionmaker(dead_engine, expire_on_commit=False, class_=AsyncSession),
    )
    response = await client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}  # no error text leaks
