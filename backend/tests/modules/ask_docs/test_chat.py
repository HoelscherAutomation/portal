from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

import app.database as db_module
from app.models import AskDocsQuery
from app.modules.ask_docs.chat import ChatOrchestrator


def _fake_emb_and_store(chunks: list[dict]):
    fake_emb = type("FakeEmb", (), {})()
    fake_emb.embed = AsyncMock(return_value=[0.1] * 768)
    fake_emb.aclose = AsyncMock()

    fake_store = type("FakeStore", (), {})()
    fake_store.search = AsyncMock(return_value=chunks)
    fake_store.aclose = AsyncMock()

    return fake_emb, fake_store


def _fake_llm(deltas: list[str], usage: dict | None = None):
    fake = type("FakeLLM", (), {})()

    async def _stream(*, system, user, max_tokens, on_final_usage=None):
        for d in deltas:
            yield d
        if on_final_usage and usage:
            on_final_usage(usage)

    fake.stream_chat = _stream
    return fake


class _FakeReranker:
    """Records calls; returns the input sources unchanged (acts as a no-op pass-through)."""
    def __init__(self):
        self.calls: list[tuple[str, list, int]] = []

    def rerank(self, query, sources, top_n):
        self.calls.append((query, list(sources), top_n))
        return list(sources)[:top_n]


async def test_orchestrator_streams_and_persists():
    chunks = [
        {"doc_id": "d1", "page_num": 3, "chunk_index": 0, "content": "Carryover is 5 days.", "source_path": "handbook.pdf"},
    ]
    fake_emb, fake_store = _fake_emb_and_store(chunks)
    fake_llm = _fake_llm(["The ", "carryover ", "is 5 days [1]."], usage={"input_tokens": 100, "output_tokens": 8})

    orch = ChatOrchestrator(
        embeddings=fake_emb,
        vectorstore=fake_store,
        llm=fake_llm,
        llm_mode="anthropic",
        top_k=8,
        max_answer_tokens=1024,
    )

    events = []
    async for ev in orch.run(query="What's PTO carryover?", user_id=None):
        events.append(ev)

    types = [ev["type"] for ev in events]
    assert types[0] == "sources"
    assert types[-1] == "final"
    assert any(t == "delta" for t in types)

    final = events[-1]
    assert final["citations"] == [1]
    assert "carryover is 5 days" in final["answer"].lower()

    async with db_module.async_session_maker() as session:
        rows = (await session.execute(select(AskDocsQuery))).scalars().all()
        assert len(rows) == 1
        assert rows[0].query_text == "What's PTO carryover?"
        assert rows[0].citation_count == 1
        assert rows[0].llm_mode == "anthropic"
        assert rows[0].tokens_used == 108
        assert rows[0].sources_used == [
            {"number": 1, "filename": "handbook.pdf", "page_num": 3, "content": "Carryover is 5 days."}
        ]


async def test_close_clients_closes_llm_too():
    """Regression: close_clients() must close the LLM client (httpx pool leak otherwise)."""
    closed: list[str] = []

    class FakeClient:
        def __init__(self, name: str):
            self.name = name
        async def aclose(self):
            closed.append(self.name)

    orch = ChatOrchestrator(
        embeddings=FakeClient("emb"),
        vectorstore=FakeClient("vs"),
        llm=FakeClient("llm"),
        llm_mode="anthropic",
        top_k=8,
        max_answer_tokens=1024,
    )
    await orch.close_clients()
    assert sorted(closed) == ["emb", "llm", "vs"]


async def test_close_clients_tolerates_clients_without_aclose():
    """Some ChatClient impls might not need aclose; hasattr guard should skip them silently."""
    closed: list[str] = []

    class WithClose:
        async def aclose(self):
            closed.append("emb")

    class NoClose:
        pass

    orch = ChatOrchestrator(
        embeddings=WithClose(),
        vectorstore=NoClose(),
        llm=NoClose(),
        llm_mode="anthropic",
        top_k=8,
        max_answer_tokens=1024,
    )
    await orch.close_clients()
    assert closed == ["emb"]


async def test_orchestrator_applies_hallucination_guard():
    fake_emb, fake_store = _fake_emb_and_store([])
    fake_llm = _fake_llm(["Based on the policies, you can do X, Y, and Z which are listed in section 3."])

    orch = ChatOrchestrator(
        embeddings=fake_emb,
        vectorstore=fake_store,
        llm=fake_llm,
        llm_mode="anthropic",
        top_k=8,
        max_answer_tokens=1024,
    )

    events = []
    async for ev in orch.run(query="What can I do?", user_id=None):
        events.append(ev)

    final = events[-1]
    assert "don't have enough information" in final["answer"].lower()
    assert final["citations"] == []


async def test_orchestrator_skips_reranker_when_disabled():
    """When reranker_enabled=False, retrieve_sources is called with self._top_k and reranker is never invoked."""
    chunks = [{"doc_id": "d", "page_num": 1, "chunk_index": 0, "content": "c", "source_path": "f.pdf"}]
    fake_emb, fake_store = _fake_emb_and_store(chunks)
    fake_llm = _fake_llm(["ok"])
    fake_rr = _FakeReranker()

    orch = ChatOrchestrator(
        embeddings=fake_emb, vectorstore=fake_store, llm=fake_llm,
        llm_mode="anthropic", top_k=8, max_answer_tokens=1024,
        reranker=fake_rr, reranker_enabled=False, pre_rerank_top_k=24,
    )
    async for _ in orch.run(query="q", user_id=None):
        pass

    fake_store.search.assert_awaited_once()
    # search was called with top_k=8 (the LLM-bound top_k), NOT 24
    assert fake_store.search.await_args.kwargs["top_k"] == 8
    assert fake_rr.calls == []  # reranker untouched


async def test_orchestrator_uses_reranker_when_enabled():
    """When reranker_enabled=True, retrieve_sources is called with pre_rerank_top_k and reranker is invoked."""
    chunks = [
        {"doc_id": f"d{i}", "page_num": 1, "chunk_index": 0, "content": f"c{i}", "source_path": f"f{i}.pdf"}
        for i in range(24)
    ]
    fake_emb, fake_store = _fake_emb_and_store(chunks)
    fake_llm = _fake_llm(["ok"])
    fake_rr = _FakeReranker()

    orch = ChatOrchestrator(
        embeddings=fake_emb, vectorstore=fake_store, llm=fake_llm,
        llm_mode="anthropic", top_k=8, max_answer_tokens=1024,
        reranker=fake_rr, reranker_enabled=True, pre_rerank_top_k=24,
    )
    async for _ in orch.run(query="my-query", user_id=None):
        pass

    # Qdrant search ran with top_k=24 (pre-rerank candidate pool)
    assert fake_store.search.await_args.kwargs["top_k"] == 24
    # Reranker ran exactly once with all 24 candidates and top_n=8
    assert len(fake_rr.calls) == 1
    q, srcs, top_n = fake_rr.calls[0]
    assert q == "my-query"
    assert len(srcs) == 24
    assert top_n == 8
