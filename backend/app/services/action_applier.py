"""Apply phone-home actions to the portal's local DB.

Each handler is idempotent. Returns a dict suitable for posting to OC's ack endpoint.
"""
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModuleEnablement, ModuleRequest

logger = logging.getLogger(__name__)

_MAX_DETAIL_CHARS = 500


def _cap(s: str) -> str:
    return s if len(s) <= _MAX_DETAIL_CHARS else s[: _MAX_DETAIL_CHARS - 3] + "..."


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
            return {"result": "error", "detail": _cap(f"Unknown action type: {action_type}")}
    except KeyError as exc:
        logger.error("Missing required payload key for action %s: %s", action_type, exc)
        return {"result": "error", "detail": _cap(f"Missing payload key: {exc}")}
    except ValueError as exc:
        logger.error("Invalid action %s: %s", action_type, exc)
        return {"result": "error", "detail": _cap(str(exc))}
    except IntegrityError as exc:
        logger.error("DB integrity error applying action %s", action_type, exc_info=exc)
        return {"result": "error", "detail": _cap("DB constraint violation")}

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
