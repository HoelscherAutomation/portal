"""Phone-home client. Sends heartbeats to the Operator Console every N seconds.

Opt-in: if OC_URL is unset, the background loop never starts.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModuleEnablement, ModuleRequest, User

logger = logging.getLogger(__name__)


# Module-level observability state for the phone-home loop
_phone_home_state = {
    "last_heartbeat_ok_at": None,  # datetime | None
    "consecutive_failures": 0,
    "loop_crashes": 0,
}


def get_phone_home_status() -> dict:
    """Return current phone-home loop state for /api/health."""
    return dict(_phone_home_state)


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
from datetime import datetime, timezone

import httpx

import app.database as db_module
from app.services.action_applier import apply_action


def _categorize_httpx_error(exc: Exception) -> str:
    """Map an httpx exception to a short category string for the summary."""
    if isinstance(exc, httpx.HTTPStatusError):
        return "http_status"
    if isinstance(exc, httpx.ConnectError):
        return "network"
    if isinstance(exc, httpx.TimeoutException):
        return "network"
    if isinstance(exc, httpx.ProtocolError):
        return "protocol"
    if isinstance(exc, httpx.NetworkError):
        # NetworkError covers TLS-ish failures too; keep "network" as the catch-all.
        return "network"
    return "other"


async def run_one_cycle(
    *,
    oc_url: str,
    oc_token: str,
    portal_version: str,
    uptime_s: int,
    http_client: httpx.AsyncClient | None = None,
) -> dict:
    """Run one phone-home cycle. Returns a summary dict for logging."""
    summary = {
        "actions_received": 0,
        "actions_acked_ok": 0,
        "actions_acked_error": 0,
        "error": None,
        "error_category": None,
    }

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
        except (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.HTTPStatusError,
            httpx.NetworkError,
            httpx.ProtocolError,
        ) as exc:
            summary["error"] = f"heartbeat POST failed: {exc}"
            summary["error_category"] = _categorize_httpx_error(exc)
            _phone_home_state["consecutive_failures"] += 1
            return summary
        except httpx.HTTPError as exc:
            # Catch-all for any other httpx error we didn't explicitly enumerate.
            summary["error"] = f"heartbeat POST failed: {exc}"
            summary["error_category"] = "other"
            _phone_home_state["consecutive_failures"] += 1
            return summary

        # Heartbeat succeeded — reset failure counter.
        _phone_home_state["last_heartbeat_ok_at"] = datetime.now(timezone.utc)
        _phone_home_state["consecutive_failures"] = 0

        try:
            body = response.json()
        except (httpx.DecodingError, ValueError) as exc:
            summary["error"] = f"heartbeat response not valid JSON: {exc}"
            summary["error_category"] = "protocol"
            return summary

        actions = body.get("actions", [])
        summary["actions_received"] = len(actions)

        for action in actions:
            action_id = action.get("id")
            action_type = action.get("type")

            # Per-action isolation: a failure in one action must not abandon the batch.
            try:
                async with db_module.async_session_maker() as session:
                    ack = await apply_action(session, action)
                    await session.commit()
            except Exception as exc:
                logger.exception(
                    "Per-action commit failed for action id=%s type=%s",
                    action_id,
                    action_type,
                )
                ack = {
                    "result": "error",
                    "detail": f"commit failed: {type(exc).__name__}: {exc}",
                }

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
            except (
                httpx.ConnectError,
                httpx.TimeoutException,
                httpx.HTTPStatusError,
                httpx.NetworkError,
                httpx.ProtocolError,
                httpx.HTTPError,
            ) as exc:
                # Action is already applied locally; log at error since OC will
                # not learn the outcome until the next cycle (if at all).
                logger.error(
                    "Failed to POST ack for action id=%s type=%s: %s",
                    action_id,
                    action_type,
                    exc,
                )

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
                logger.warning(
                    "Phone-home cycle failed (%s): %s",
                    summary.get("error_category") or "unknown",
                    summary["error"],
                )
            elif summary["actions_received"] == 0:
                # Quiet path — most cycles look like this; demote to DEBUG.
                logger.debug(
                    "Phone-home cycle: actions=%d ok=%d err=%d",
                    summary["actions_received"],
                    summary["actions_acked_ok"],
                    summary["actions_acked_error"],
                )
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
            _phone_home_state["loop_crashes"] += 1
            logger.exception("Phone-home cycle crashed (continuing)")

        await asyncio.sleep(interval_seconds)
