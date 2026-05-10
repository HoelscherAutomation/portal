"""Apply phone-home actions to the portal's local DB.

Each handler is idempotent. Returns a dict suitable for posting to OC's ack endpoint.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModuleEnablement, ModuleRequest

logger = logging.getLogger(__name__)


async def apply_action(session: AsyncSession, action: dict) -> dict:
    """Dispatch one action to its handler. Caller must commit. Returns ack dict."""
    action_type = action.get("type")
    payload = action.get("payload") or {}

    try:
        if action_type == "enable_module":
            await _enable_module(session, payload)
        elif action_type == "disable_module":
            await _disable_module(session, payload)
        elif action_type == "mark_request_fulfilled":
            await _mark_request_fulfilled(session, payload)
        else:
            return {"result": "error", "detail": f"Unknown action type: {action_type}"}
    except Exception as exc:
        logger.exception("Failed to apply action %s", action_type)
        return {"result": "error", "detail": f"{type(exc).__name__}: {exc}"}

    return {"result": "ok"}


async def _enable_module(session: AsyncSession, payload: dict) -> None:
    module_key = payload["module_key"]
    existing = (
        await session.execute(select(ModuleEnablement).where(ModuleEnablement.module_key == module_key))
    ).scalar_one_or_none()
    if existing is None:
        session.add(ModuleEnablement(module_key=module_key, enabled=True))
    else:
        existing.enabled = True


async def _disable_module(session: AsyncSession, payload: dict) -> None:
    module_key = payload["module_key"]
    existing = (
        await session.execute(select(ModuleEnablement).where(ModuleEnablement.module_key == module_key))
    ).scalar_one_or_none()
    if existing is None:
        return  # No-op
    existing.enabled = False


async def _mark_request_fulfilled(session: AsyncSession, payload: dict) -> None:
    request_id = payload["portal_request_id"]
    req = await session.get(ModuleRequest, request_id)
    if req is None:
        raise ValueError(f"ModuleRequest id={request_id} not found")
    req.fulfilled = True
