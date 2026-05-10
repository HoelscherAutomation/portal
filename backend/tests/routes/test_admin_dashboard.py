import pytest
from httpx import AsyncClient

from tests.test_auth import _create_user


async def _login(client: AsyncClient, *, superuser=True):
    email = "admin@example.com" if superuser else "user@example.com"
    await _create_user(email, "test-password-123", superuser=superuser)
    r = await client.post("/api/auth/login", data={"username": email, "password": "test-password-123"})
    assert r.status_code in (200, 204)


async def test_dashboard_requires_superuser(client: AsyncClient):
    r = await client.get("/api/admin/modules/ask-docs/dashboard")
    assert r.status_code == 401
    await _login(client, superuser=False)
    r = await client.get("/api/admin/modules/ask-docs/dashboard")
    assert r.status_code == 403


async def test_dashboard_returns_zero_state(client: AsyncClient):
    await _login(client)
    r = await client.get("/api/admin/modules/ask-docs/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["documents"]["total"] == 0
    assert body["queries_30d"]["count"] == 0
    assert body["queries_30d"]["cost_usd_estimated"] == 0.0
    assert len(body["queries_30d"]["tokens_per_day"]) == 30
    assert body["update_banner"] is None


async def test_dashboard_returns_full_payload_shape(client: AsyncClient):
    await _login(client)
    r = await client.get("/api/admin/modules/ask-docs/dashboard")
    body = r.json()
    # Spot-check the spec'd shape — all keys present
    assert set(body.keys()) == {"documents", "queries_30d", "update_banner"}
    assert set(body["documents"].keys()) == {"total", "by_status", "total_chunks"}
    assert set(body["queries_30d"].keys()) >= {
        "count", "tokens", "cost_usd_estimated", "by_mode",
        "tokens_per_day", "avg_latency_ms", "p95_latency_ms",
    }
