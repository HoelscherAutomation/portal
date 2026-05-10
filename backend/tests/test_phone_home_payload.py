from datetime import datetime, timezone

from app.models import ModuleEnablement, ModuleRequest
from app.services.phone_home import build_heartbeat_payload

import app.database as db_module


async def test_payload_with_no_modules_or_requests():
    async with db_module.async_session_maker() as session:
        payload = await build_heartbeat_payload(session, version="0.5.0", uptime_s=42)

    assert payload["version"] == "0.5.0"
    assert payload["modules_enabled"] == []
    assert payload["pending_requests"] == []
    assert payload["uptime_s"] == 42


async def test_payload_includes_enabled_modules():
    async with db_module.async_session_maker() as session:
        session.add(ModuleEnablement(module_key="ask-docs", enabled=True))
        session.add(ModuleEnablement(module_key="announcements", enabled=False))  # disabled — excluded
        await session.commit()

        payload = await build_heartbeat_payload(session, version="0.5.0", uptime_s=0)

    assert payload["modules_enabled"] == ["ask-docs"]


async def test_payload_includes_pending_requests():
    requested_at = datetime.now(timezone.utc).replace(tzinfo=None)
    async with db_module.async_session_maker() as session:
        from app.auth.manager import UserManager, get_user_db
        from app.auth.schemas import UserCreate
        async for user_db in get_user_db(session):
            manager = UserManager(user_db)
            user = await manager.create(
                UserCreate(email="req@example.com", password="test-password-123", is_active=True),
                safe=False,
            )
            break

        session.add(ModuleRequest(
            module_key="onboarding",
            requested_by=user.id,
            requested_at=requested_at,
            fulfilled=False,
        ))
        session.add(ModuleRequest(
            module_key="forms",
            requested_by=user.id,
            requested_at=requested_at,
            fulfilled=True,  # already fulfilled — excluded
        ))
        await session.commit()

        payload = await build_heartbeat_payload(session, version="0.5.0", uptime_s=0)

    assert len(payload["pending_requests"]) == 1
    assert payload["pending_requests"][0]["module_key"] == "onboarding"
    assert payload["pending_requests"][0]["requested_by_email"] == "req@example.com"
