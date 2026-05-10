from typing import Any

import httpx

import app.database as db_module
from app.models import ModuleEnablement
from app.services.phone_home import run_one_cycle


class _FakeResponse:
    def __init__(self, status_code: int, body: Any):
        self.status_code = status_code
        self._body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self):
        return self._body


class _FakeClient:
    """Minimal httpx.AsyncClient stand-in."""

    def __init__(self, post_handler):
        self._post_handler = post_handler

    async def post(self, url: str, *, json: dict, headers: dict) -> _FakeResponse:
        return await self._post_handler(url, json, headers)

    async def aclose(self):
        pass


async def test_cycle_sends_payload_and_returns_summary():
    captured = {}

    async def handle(url, body, headers):
        if url.endswith("/api/phone-home"):
            captured["payload"] = body
            captured["auth"] = headers["Authorization"]
            return _FakeResponse(200, {"actions": [], "next_poll_after": "2026-05-10T22:35:00Z"})
        raise AssertionError(f"unexpected url {url}")

    summary = await run_one_cycle(
        oc_url="http://oc.test",
        oc_token="pt_test_token",
        portal_version="0.9.9",
        uptime_s=12345,
        http_client=_FakeClient(handle),
    )

    assert summary["actions_received"] == 0
    assert summary["error"] is None
    assert captured["auth"] == "Bearer pt_test_token"
    assert captured["payload"]["version"] == "0.9.9"
    assert captured["payload"]["uptime_s"] == 12345


async def test_cycle_applies_returned_actions_and_acks():
    ack_calls = []

    async def handle(url, body, headers):
        if url.endswith("/api/phone-home"):
            return _FakeResponse(200, {
                "actions": [
                    {"id": "act-1", "type": "enable_module", "payload": {"module_key": "ask-docs"}},
                    {"id": "act-2", "type": "weird_action", "payload": {}},
                ],
                "next_poll_after": "2026-05-10T22:35:00Z",
            })
        if "/api/phone-home/ack/" in url:
            ack_calls.append((url, body))
            return _FakeResponse(204, None)
        raise AssertionError(f"unexpected url {url}")

    summary = await run_one_cycle(
        oc_url="http://oc.test",
        oc_token="pt_test_token",
        portal_version="0.5.0",
        uptime_s=0,
        http_client=_FakeClient(handle),
    )

    assert summary["actions_received"] == 2
    assert summary["actions_acked_ok"] == 1
    assert summary["actions_acked_error"] == 1

    # Verify enable_module was applied to portal DB
    from sqlalchemy import select
    async with db_module.async_session_maker() as session:
        rows = (await session.execute(select(ModuleEnablement))).scalars().all()
        assert len(rows) == 1
        assert rows[0].module_key == "ask-docs"
        assert rows[0].enabled is True

    # Verify both acks were posted
    assert len(ack_calls) == 2
    ack_results = sorted(call[1]["result"] for call in ack_calls)
    assert ack_results == ["error", "ok"]


async def test_cycle_handles_oc_unreachable_gracefully():
    async def handle(url, body, headers):
        raise httpx.ConnectError("connection refused")

    summary = await run_one_cycle(
        oc_url="http://oc.test",
        oc_token="pt_test_token",
        portal_version="0.5.0",
        uptime_s=0,
        http_client=_FakeClient(handle),
    )

    assert summary["error"] is not None
    assert summary["actions_received"] == 0
