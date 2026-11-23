import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_active_user
from app.database import get_async_session
from app.models import User
from app.services.phone_home import get_phone_home_status

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health(session: AsyncSession = Depends(get_async_session)) -> dict:
    """Public health probe. Intentionally minimal — returns no internal state.

    Runs `SELECT 1` and answers 503 when the database cannot be reached, so
    the container healthcheck stops reporting healthy while every real
    request would fail. Caddy / external monitors hit this without auth.
    Operational state (phone_home connectivity, OC reachability, etc.) is
    exposed only on the auth-gated /api/health/internal below.
    """
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        # Connection failures arrive as OSError as well as SQLAlchemyError.
        logger.error("health: database unreachable: %r", exc)
        raise HTTPException(status_code=503, detail="database unavailable") from None
    return {"status": "ok"}


@router.get("/health/internal")
async def health_internal(_user: User = Depends(current_active_user)) -> dict:
    """Internal health view — includes phone-home connectivity state.
    Auth required so we don't leak OC reachability to unauthenticated probes.
    """
    return {
        "status": "ok",
        "phone_home": get_phone_home_status(),
    }
