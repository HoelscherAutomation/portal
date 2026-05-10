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


import asyncio

import httpx

import app.database as db_module
from app.services.action_applier import apply_action


async def run_one_cycle(
    *,
    oc_url: str,
    oc_token: str,
    portal_version: str,
    uptime_s: int,
    http_client: httpx.AsyncClient | None = None,
) -> dict:
    """Run one phone-home cycle. Returns a summary dict for logging."""
    summary = {"actions_received": 0, "actions_acked_ok": 0, "actions_acked_error": 0, "error": None}

    own_client = http_client is None
    client = http_client or httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
    )

    try:
        async with db_module.async_session_maker() as session:
            payload = await build_heartbeat_payload(session, version=portal_version, uptime_s=uptime_s)

        try:
            response = await client.post(
                f"{oc_url}/api/phone-home",
                json=payload,
                headers={"Authorization": f"Bearer {oc_token}"},
            )
            response.raise_for_status()
        except (httpx.HTTPError, httpx.HTTPStatusError) as exc:
            summary["error"] = f"heartbeat POST failed: {exc}"
            return summary

        body = response.json()
        actions = body.get("actions", [])
        summary["actions_received"] = len(actions)

        for action in actions:
            action_id = action["id"]
            async with db_module.async_session_maker() as session:
                ack = await apply_action(session, action)
                await session.commit()

            try:
                ack_resp = await client.post(
                    f"{oc_url}/api/phone-home/ack/{action_id}",
                    json=ack,
                    headers={"Authorization": f"Bearer {oc_token}"},
                )
                ack_resp.raise_for_status()
                if ack["result"] == "ok":
                    summary["actions_acked_ok"] += 1
                else:
                    summary["actions_acked_error"] += 1
            except (httpx.HTTPError, httpx.HTTPStatusError) as exc:
                logger.warning("Failed to POST ack for action %s: %s", action_id, exc)

    finally:
        if own_client:
            await client.aclose()

    return summary


async def phone_home_loop(
    *,
    oc_url: str,
    oc_token: str,
    portal_version: str,
    interval_seconds: int,
    started_at: float,
    initial_delay_seconds: int = 30,
) -> None:
    """Forever loop: run one cycle every interval_seconds."""
    import time

    logger.info("Phone-home loop starting, first cycle in %ss", initial_delay_seconds)
    await asyncio.sleep(initial_delay_seconds)

    while True:
        uptime_s = int(time.monotonic() - started_at)
        try:
            summary = await run_one_cycle(
                oc_url=oc_url,
                oc_token=oc_token,
                portal_version=portal_version,
                uptime_s=uptime_s,
            )
            if summary["error"]:
                logger.warning("Phone-home cycle: %s", summary["error"])
            else:
                logger.info(
                    "Phone-home cycle: actions=%d ok=%d err=%d",
                    summary["actions_received"],
                    summary["actions_acked_ok"],
                    summary["actions_acked_error"],
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Phone-home cycle crashed (continuing)")

        await asyncio.sleep(interval_seconds)
