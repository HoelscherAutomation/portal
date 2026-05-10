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
