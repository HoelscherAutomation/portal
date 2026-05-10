"""Phone-home client. Sends heartbeats to the Operator Console every N seconds.

Opt-in: if OC_URL is unset, the background loop never starts.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModuleEnablement, ModuleRequest, User

logger = logging.getLogger(__name__)


async def build_heartbeat_payload(
    session: AsyncSession,
    *,
    version: str,
    uptime_s: int,
) -> dict:
    """Build the JSON payload for a phone-home heartbeat from current portal state."""

    # Enabled modules
    enabled_rows = (
        await session.execute(
            select(ModuleEnablement).where(ModuleEnablement.enabled.is_(True))
        )
    ).scalars().all()
    modules_enabled = [row.module_key for row in enabled_rows]

    # Pending requests, joined with the requester's email
    request_rows = (
        await session.execute(
            select(ModuleRequest, User.email)
            .join(User, ModuleRequest.requested_by == User.id, isouter=True)
            .where(ModuleRequest.fulfilled.is_(False))
            .order_by(ModuleRequest.requested_at)
        )
    ).all()

    pending_requests = []
    for req, email in request_rows:
        if req.requested_at.tzinfo is None:
            iso = req.requested_at.isoformat() + "Z"
        else:
            iso = req.requested_at.isoformat()
        pending_requests.append({
            "id": req.id,
            "module_key": req.module_key,
            "requested_by_email": email or "unknown@portal.local",
            "requested_at": iso,
        })

    return {
        "version": version,
        "modules_enabled": modules_enabled,
        "pending_requests": pending_requests,
        "uptime_s": uptime_s,
    }
