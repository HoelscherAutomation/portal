from httpx import AsyncClient

from app.auth.manager import UserManager, get_user_db
from app.auth.schemas import UserCreate
from app.database import get_async_session


async def test_tenant_config_unauthenticated_returns_401(client: AsyncClient):
    response = await client.get("/api/tenant/config")
    assert response.status_code == 401


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


async def test_tenant_config_authenticated_returns_default(client: AsyncClient):
    await _create_user("user@example.com", "test-password-123")
    await _login(client, "user@example.com", "test-password-123")

    response = await client.get("/api/tenant/config")
    assert response.status_code == 200
    body = response.json()
    assert body["company_name"] == "My Company"
    assert body["primary_color"] == "#6dd5fa"
    assert body["logo_filename"] is None
