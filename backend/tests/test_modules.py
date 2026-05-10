from httpx import AsyncClient

from app.auth.manager import UserManager, get_user_db
from app.auth.schemas import UserCreate
from app.database import get_async_session


async def _create_user(email: str, password: str, *, superuser: bool = False) -> None:
    async for session in get_async_session():
        async for user_db in get_user_db(session):
            manager = UserManager(user_db)
            await manager.create(
                UserCreate(
                    email=email,
                    password=password,
                    is_active=True,
                    is_superuser=superuser,
                ),
                safe=False,
            )
            break
        break


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
