import json

import pytest
from httpx import AsyncClient

from tests.test_auth import _create_user


async def _login(client: AsyncClient) -> None:
    await _create_user("admin@example.com", "test-password-123", superuser=True)
    response = await client.post(
        "/api/auth/login",
        data={"username": "admin@example.com", "password": "test-password-123"},
    )
    assert response.status_code in (200, 204)


async def test_chat_requires_auth(client: AsyncClient):
    response = await client.post("/api/modules/ask-docs/chat", json={"query": "hi"})
    assert response.status_code == 401


async def test_chat_rejects_empty_query(client: AsyncClient, monkeypatch):
    # Avoid 503 by stubbing orchestrator construction (settings has no API key in test)
    async def _fake_make():
        return None
    monkeypatch.setattr(
        "app.modules.ask_docs.routes._make_orchestrator",
        _fake_make,
    )
    await _login(client)
    response = await client.post("/api/modules/ask-docs/chat", json={"query": "   "})
    assert response.status_code == 400


async def test_chat_streams_sse_events(client: AsyncClient, monkeypatch):
    """End-to-end SSE: orchestrator is mocked to emit a deterministic stream."""

    class FakeOrch:
        async def run(self, *, query, user_id, filters=None):
            yield {"type": "sources", "sources": [{"number": 1, "filename": "a.pdf", "page_num": 1, "content": "x"}]}
            yield {"type": "delta", "text": "Hello "}
            yield {"type": "delta", "text": "world."}
            yield {"type": "final", "answer": "Hello world.", "citations": []}

        async def close_clients(self):
            return None

    async def _fake_make():
        return FakeOrch()
    monkeypatch.setattr(
        "app.modules.ask_docs.routes._make_orchestrator",
        _fake_make,
    )

    await _login(client)
    response = await client.post(
        "/api/modules/ask-docs/chat",
        json={"query": "say hi"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    body = response.text
    events = [json.loads(line[len("data: "):]) for line in body.split("\n\n") if line.startswith("data: ")]
    types = [e["type"] for e in events]
    assert types == ["sources", "delta", "delta", "final"]


async def test_chat_emits_error_event_on_orchestrator_failure(client: AsyncClient, monkeypatch):
    """If orchestrator.run() raises mid-stream (e.g., LLM 4xx), the SSE stream emits an error event."""

    class FailingOrch:
        async def run(self, *, query, user_id, filters=None):
            yield {"type": "sources", "sources": []}
            raise RuntimeError("simulated LLM 400: credit balance too low")

        async def close_clients(self):
            return None

    async def _fake_make():
        return FailingOrch()
    monkeypatch.setattr(
        "app.modules.ask_docs.routes._make_orchestrator",
        _fake_make,
    )

    await _login(client)
    response = await client.post(
        "/api/modules/ask-docs/chat",
        json={"query": "anything"},
    )
    assert response.status_code == 200

    body = response.text
    events = [json.loads(line[len("data: "):]) for line in body.split("\n\n") if line.startswith("data: ")]
    types = [e["type"] for e in events]
    assert types == ["sources", "error"]
    assert "credit balance too low" in events[-1]["detail"]


async def test_get_chunk_returns_payload(client: AsyncClient, monkeypatch):
    """GET /chunks/{doc_id}/{chunk_index} fetches a single chunk's payload from Qdrant."""
    captured = {}

    class FakeVS:
        async def search_by_doc_chunk(self, *, doc_id, chunk_index):
            captured["doc_id"] = doc_id
            captured["chunk_index"] = chunk_index
            return {
                "doc_id": doc_id,
                "page_num": 5,
                "chunk_index": chunk_index,
                "content": "the chunk content",
                "source_path": "doc.pdf",
            }
        async def aclose(self):
            pass

    monkeypatch.setattr(
        "app.modules.ask_docs.routes._make_vectorstore",
        lambda: FakeVS(),
    )

    await _login(client)
    response = await client.get("/api/modules/ask-docs/chunks/some-doc-id/3")
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "the chunk content"
    assert body["page_num"] == 5
    assert captured == {"doc_id": "some-doc-id", "chunk_index": 3}


async def test_chat_route_rejects_unknown_filter_field(client: AsyncClient, monkeypatch):
    """Unknown fields inside filters should 422 (extra='forbid' on RetrievalFilters)."""
    # Stub the orchestrator factory so we don't fail with 503 due to missing LLM config.
    async def _fake_make():
        return None
    monkeypatch.setattr(
        "app.modules.ask_docs.routes._make_orchestrator",
        _fake_make,
    )
    await _login(client)
    response = await client.post(
        "/api/modules/ask-docs/chat",
        json={"query": "hello", "filters": {"filename": ["foo.pdf"]}},
    )
    assert response.status_code == 422


async def test_chat_route_rejects_inverted_date_range(client: AsyncClient, monkeypatch):
    """uploaded_after >= uploaded_before should 422 via the model_validator."""
    async def _fake_make():
        return None
    monkeypatch.setattr(
        "app.modules.ask_docs.routes._make_orchestrator",
        _fake_make,
    )
    await _login(client)
    response = await client.post(
        "/api/modules/ask-docs/chat",
        json={
            "query": "hello",
            "filters": {
                "uploaded_after": "2026-06-01T00:00:00Z",
                "uploaded_before": "2026-01-01T00:00:00Z",
            },
        },
    )
    assert response.status_code == 422


async def test_chat_route_accepts_filters(client: AsyncClient, monkeypatch):
    """A request with valid filters reaches the orchestrator and returns SSE 200."""

    captured: dict = {}

    class FakeOrch:
        async def run(self, *, query, user_id, filters=None):
            captured["query"] = query
            captured["filters"] = filters
            yield {"type": "sources", "sources": []}
            yield {"type": "final", "answer": "ok", "citations": []}

        async def close_clients(self):
            return None

    async def _fake_make():
        return FakeOrch()
    monkeypatch.setattr(
        "app.modules.ask_docs.routes._make_orchestrator",
        _fake_make,
    )

    await _login(client)
    response = await client.post(
        "/api/modules/ask-docs/chat",
        json={
            "query": "hello",
            "filters": {"doc_ids": ["nonexistent-doc-id"]},
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    # The orchestrator received a RetrievalFilters with the doc_ids list
    assert captured["filters"] is not None
    assert captured["filters"].doc_ids == ["nonexistent-doc-id"]
