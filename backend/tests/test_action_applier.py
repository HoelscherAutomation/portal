from datetime import datetime, timezone

from sqlalchemy import select

from app.models import ModuleEnablement, ModuleRequest
from app.services.action_applier import apply_action

import app.database as db_module


async def test_apply_enable_module_creates_row():
    action = {"type": "enable_module", "payload": {"module_key": "ask-docs"}}
    async with db_module.async_session_maker() as session:
        result = await apply_action(session, action)
        await session.commit()

        rows = (await session.execute(select(ModuleEnablement))).scalars().all()
        assert len(rows) == 1
        assert rows[0].module_key == "ask-docs"
        assert rows[0].enabled is True

    assert result == {"result": "ok"}


async def test_apply_enable_module_idempotent():
    action = {"type": "enable_module", "payload": {"module_key": "ask-docs"}}
    async with db_module.async_session_maker() as session:
        await apply_action(session, action)
        await session.commit()
        await apply_action(session, action)
        await session.commit()

        rows = (await session.execute(select(ModuleEnablement))).scalars().all()
        assert len(rows) == 1


async def test_apply_disable_module():
    async with db_module.async_session_maker() as session:
        session.add(ModuleEnablement(module_key="ask-docs", enabled=True))
        await session.commit()

        await apply_action(session, {"type": "disable_module", "payload": {"module_key": "ask-docs"}})
        await session.commit()

        row = (await session.execute(select(ModuleEnablement))).scalar_one()
        assert row.module_key == "ask-docs"
        assert row.enabled is False


async def test_apply_mark_request_fulfilled():
    from app.auth.manager import UserManager, get_user_db
    from app.auth.schemas import UserCreate

    async with db_module.async_session_maker() as session:
        async for user_db in get_user_db(session):
            manager = UserManager(user_db)
            user = await manager.create(
                UserCreate(email="x@example.com", password="test-password-123", is_active=True),
                safe=False,
            )
            break

        req = ModuleRequest(
            module_key="onboarding",
            requested_by=user.id,
            requested_at=datetime.now(timezone.utc).replace(tzinfo=None),
            fulfilled=False,
        )
        session.add(req)
        await session.commit()
        await session.refresh(req)
        request_id = req.id

        await apply_action(
            session,
            {"type": "mark_request_fulfilled", "payload": {"portal_request_id": request_id}},
        )
        await session.commit()

        refreshed = await session.get(ModuleRequest, request_id)
        assert refreshed.fulfilled is True


async def test_apply_unknown_action_returns_error():
    async with db_module.async_session_maker() as session:
        result = await apply_action(session, {"type": "weird_unknown_type", "payload": {}})

    assert result["result"] == "error"
    assert "unknown" in result["detail"].lower() or "unsupported" in result["detail"].lower()


async def test_apply_mark_fulfilled_missing_id_returns_error():
    async with db_module.async_session_maker() as session:
        result = await apply_action(
            session,
            {"type": "mark_request_fulfilled", "payload": {"portal_request_id": 99999}},
        )

    assert result["result"] == "error"
