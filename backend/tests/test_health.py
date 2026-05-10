async def test_health_returns_ok(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # Phone-home status is exposed for observability; check the keys are present.
    assert "phone_home" in body
    assert set(body["phone_home"].keys()) == {
        "last_heartbeat_ok_at",
        "consecutive_failures",
        "loop_crashes",
    }
