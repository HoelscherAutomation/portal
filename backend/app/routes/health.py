from fastapi import APIRouter, Depends

from app.auth.backend import current_active_user
from app.models import User
from app.services.phone_home import get_phone_home_status

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Public liveness probe. Intentionally minimal — returns no internal state.

    Caddy / external monitors hit this without auth. Operational state
    (phone_home connectivity, OC reachability, etc.) is exposed only on
    the auth-gated /api/health/internal below.
    """
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
