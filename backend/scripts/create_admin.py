"""Bootstrap the initial admin user. Run via:

    docker compose exec backend python -m scripts.create_admin
"""
import asyncio
import getpass
import sys

from app.auth.manager import UserManager, get_user_db
from app.auth.schemas import UserCreate
from app.database import get_async_session


async def create_admin(email: str, password: str) -> None:
    async for session in get_async_session():
        async for user_db in get_user_db(session):
            manager = UserManager(user_db)
            user = await manager.create(
                UserCreate(
                    email=email,
                    password=password,
                    is_active=True,
                    is_superuser=True,
                    is_verified=True,
                ),
                safe=False,
            )
            print(f"Created admin user: {user.email} (id={user.id})")
            return


def main() -> int:
    email = input("Admin email: ").strip()
    if not email:
        print("Email is required.", file=sys.stderr)
        return 1
    password = getpass.getpass("Admin password: ")
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1
    asyncio.run(create_admin(email, password))
    return 0


if __name__ == "__main__":
    sys.exit(main())
