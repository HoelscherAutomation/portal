from httpx import AsyncClient

from tests.test_auth import _create_user


async def _login(client: AsyncClient, email: str, password: str) -> None:
    response = await client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )
    assert response.status_code in (200, 204)


async def test_modules_unauthenticated_returns_401(client: AsyncClient):
    response = await client.get("/api/modules")
    assert response.status_code == 401


async def test_modules_authenticated_returns_seven(client: AsyncClient):
    await _create_user("user@example.com", "test-password-123")
    await _login(client, "user@example.com", "test-password-123")

    response = await client.get("/api/modules")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 7

    keys = [m["key"] for m in body]
    assert "ask-docs" in keys
    assert "announcements" in keys
    assert "forms" in keys


async def test_modules_default_state_all_disabled(client: AsyncClient):
    await _create_user("user@example.com", "test-password-123")
    await _login(client, "user@example.com", "test-password-123")

    response = await client.get("/api/modules")
    body = response.json()
    for module in body:
        assert module["enabled"] is False
        assert module["has_pending_request"] is False


async def test_request_module_unauthenticated_returns_401(client: AsyncClient):
    response = await client.post("/api/modules/announcements/request")
    assert response.status_code == 401


async def test_request_module_creates_pending(client: AsyncClient):
    await _create_user("admin@example.com", "test-password-123", superuser=True)
    await _login(client, "admin@example.com", "test-password-123")

    response = await client.post("/api/modules/announcements/request")
    assert response.status_code == 201

    listing = await client.get("/api/modules")
    body = listing.json()
    announcements = next(m for m in body if m["key"] == "announcements")
    assert announcements["has_pending_request"] is True


async def test_request_module_duplicate_returns_409(client: AsyncClient):
    await _create_user("admin@example.com", "test-password-123", superuser=True)
    await _login(client, "admin@example.com", "test-password-123")

    first = await client.post("/api/modules/announcements/request")
    assert first.status_code == 201

    second = await client.post("/api/modules/announcements/request")
    assert second.status_code == 409


async def test_request_module_unknown_key_returns_404(client: AsyncClient):
    await _create_user("admin@example.com", "test-password-123", superuser=True)
    await _login(client, "admin@example.com", "test-password-123")

    response = await client.post("/api/modules/no-such-module/request")
    assert response.status_code == 404


async def test_request_module_requires_superuser(client: AsyncClient):
    await _create_user("user@example.com", "test-password-123")  # not superuser
    await _login(client, "user@example.com", "test-password-123")

    response = await client.post("/api/modules/announcements/request")
    assert response.status_code == 403
