from unittest.mock import AsyncMock

import pytest

from app.modules.ask_docs.prompts import FormattedSource
from app.modules.ask_docs.retrieval import retrieve_sources


async def test_retrieves_and_formats_sources():
    fake_emb = type("FakeEmb", (), {})()
    fake_emb.embed = AsyncMock(return_value=[0.1] * 768)
    fake_emb.aclose = AsyncMock()

    fake_store = type("FakeStore", (), {})()
    fake_store.search = AsyncMock(return_value=[
        {"doc_id": "d1", "page_num": 3, "chunk_index": 0, "content": "first chunk", "source_path": "doc1.pdf"},
        {"doc_id": "d2", "page_num": 1, "chunk_index": 0, "content": "second chunk", "source_path": "doc2.pdf"},
    ])
    fake_store.aclose = AsyncMock()

    sources = await retrieve_sources(
        query="hello",
        top_k=2,
        embeddings=fake_emb,
        vectorstore=fake_store,
    )

    assert len(sources) == 2
    assert isinstance(sources[0], FormattedSource)
    assert sources[0].number == 1  # 1-indexed
    assert sources[0].filename == "doc1.pdf"
    assert sources[0].page_num == 3
    assert sources[0].content == "first chunk"
    assert sources[1].number == 2

    fake_emb.embed.assert_awaited_once_with("hello")
    fake_store.search.assert_awaited_once()


async def test_empty_when_no_chunks_indexed():
    fake_emb = type("FakeEmb", (), {})()
    fake_emb.embed = AsyncMock(return_value=[0.1] * 768)
    fake_emb.aclose = AsyncMock()

    fake_store = type("FakeStore", (), {})()
    fake_store.search = AsyncMock(return_value=[])
    fake_store.aclose = AsyncMock()

    sources = await retrieve_sources(
        query="anything",
        top_k=8,
        embeddings=fake_emb,
        vectorstore=fake_store,
    )
    assert sources == []
