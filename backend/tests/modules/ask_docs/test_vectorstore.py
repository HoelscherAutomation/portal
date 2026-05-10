import uuid
from contextlib import asynccontextmanager

import pytest

from app.modules.ask_docs.vectorstore import VectorStore

_TEST_COLLECTION = "ask_docs_chunks_test"


@pytest.fixture
def vectorstore_factory():
    """Sync fixture that returns an async context manager for a clean VectorStore.

    The underlying AsyncQdrantClient (httpx) binds asyncio primitives to the
    loop that first drives it. By deferring construction into the test's own
    event loop (via async context manager) we avoid cross-loop binding errors
    that occur when an async fixture and its test end up on different loops.
    """
    from app.config import get_settings

    @asynccontextmanager
    async def _make():
        store = VectorStore(
            url=get_settings().qdrant_url,
            collection_name=_TEST_COLLECTION,
            vector_size=4,  # tiny for tests
        )
        try:
            await store.ensure_collection()
            await store.delete_all()
            yield store
        finally:
            await store.delete_all()
            await store.aclose()

    return _make


async def test_upsert_and_search(vectorstore_factory):
    # Use orthogonal vectors so cosine similarity disambiguates results.
    # Two parallel vectors (same direction) would have identical cosine
    # similarity to any query, making top_k ordering nondeterministic.
    async with vectorstore_factory() as vectorstore:
        doc_id = uuid.uuid4()
        points = [
            {
                "vector": [1.0, 0.0, 0.0, 0.0],
                "payload": {
                    "doc_id": str(doc_id),
                    "page_num": 1,
                    "chunk_index": 0,
                    "content": "first chunk",
                    "source_path": "test.pdf",
                },
            },
            {
                "vector": [0.0, 1.0, 0.0, 0.0],
                "payload": {
                    "doc_id": str(doc_id),
                    "page_num": 1,
                    "chunk_index": 1,
                    "content": "second chunk",
                    "source_path": "test.pdf",
                },
            },
        ]
        await vectorstore.upsert(points)

        results = await vectorstore.search(query_vector=[1.0, 0.0, 0.0, 0.0], top_k=1)
        assert len(results) == 1
        assert results[0]["content"] == "first chunk"


async def test_delete_by_doc_id(vectorstore_factory):
    async with vectorstore_factory() as vectorstore:
        doc_a = uuid.uuid4()
        doc_b = uuid.uuid4()
        await vectorstore.upsert([
            {
                "vector": [1.0, 0.0, 0.0, 0.0],
                "payload": {"doc_id": str(doc_a), "page_num": 1, "chunk_index": 0, "content": "a", "source_path": "a.pdf"},
            },
            {
                "vector": [0.0, 1.0, 0.0, 0.0],
                "payload": {"doc_id": str(doc_b), "page_num": 1, "chunk_index": 0, "content": "b", "source_path": "b.pdf"},
            },
        ])
        await vectorstore.delete_by_doc_id(str(doc_a))

        results = await vectorstore.search(query_vector=[0.0, 1.0, 0.0, 0.0], top_k=10)
        assert len(results) == 1
        assert results[0]["content"] == "b"
