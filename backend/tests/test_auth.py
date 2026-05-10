from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.manager import UserManager, get_user_db
from app.auth.schemas import UserCreate
from app.database import get_async_session


async def _create_test_user(email: str, password: str) -> None:
    async for session in get_async_session():
        async for user_db in get_user_db(session):
            manager = UserManager(user_db)
            await manager.create(
                UserCreate(email=email, password=password, is_active=True),
                safe=False,
            )
            break
        break


async def test_me_unauthenticated_returns_401(client: AsyncClient):
    response = await client.get("/api/me")
    assert response.status_code == 401


async def test_login_then_me_returns_user(client: AsyncClient):
    email = "test@example.com"
    password = "test-password-123"
    await _create_test_user(email, password)

    login = await client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )
    assert login.status_code in (200, 204)

    me = await client.get("/api/me")
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == email
