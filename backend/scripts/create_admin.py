"""Bootstrap the initial admin user. Run via:

    docker compose exec backend python -m scripts.create_admin
"""
import asyncio
import getpass
import sys

from fastapi_users.exceptions import UserAlreadyExists

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
            print(f"✓ Created admin user with superuser privileges: {user.email} (id={user.id})")
            return


def main() -> int:
    email = input("Email: ").strip()
    if not email:
        print("Email is required.", file=sys.stderr)
        return 1
    password = getpass.getpass("Password: ")
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1
    confirm = getpass.getpass("Confirm: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    try:
        asyncio.run(create_admin(email, password))
    except UserAlreadyExists:
        print(f"User with email {email} already exists.", file=sys.stderr)
        return 2
    except Exception as exc:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(f"\nFailed to create admin: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
