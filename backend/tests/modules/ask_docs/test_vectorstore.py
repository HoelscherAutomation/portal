import uuid


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


from datetime import datetime, timezone

from app.modules.ask_docs.retrieval_types import RetrievalFilters
from app.modules.ask_docs.vectorstore import _build_qdrant_filter


def test_build_filter_returns_none_for_no_filters() -> None:
    assert _build_qdrant_filter(None) is None
    assert _build_qdrant_filter(RetrievalFilters()) is None


def test_build_filter_doc_ids() -> None:
    f = _build_qdrant_filter(RetrievalFilters(doc_ids=["a", "b"]))
    assert f is not None
    assert len(f.must) == 1
    assert f.must[0].key == "doc_id"


def test_build_filter_content_types() -> None:
    f = _build_qdrant_filter(RetrievalFilters(content_types=["application/pdf"]))
    assert f is not None
    assert f.must[0].key == "content_type"


def test_build_filter_uploaded_by() -> None:
    f = _build_qdrant_filter(RetrievalFilters(uploaded_by=[42]))
    assert f is not None
    assert f.must[0].key == "uploaded_by"


def test_build_filter_date_range() -> None:
    f = _build_qdrant_filter(
        RetrievalFilters(
            uploaded_after=datetime(2026, 1, 1, tzinfo=timezone.utc),
            uploaded_before=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
    )
    assert f is not None
    assert f.must[0].key == "uploaded_at"


def test_build_filter_uploaded_after_only() -> None:
    f = _build_qdrant_filter(
        RetrievalFilters(uploaded_after=datetime(2026, 1, 1, tzinfo=timezone.utc))
    )
    assert f is not None
    assert len(f.must) == 1
    assert f.must[0].key == "uploaded_at"


def test_build_filter_combines_all() -> None:
    f = _build_qdrant_filter(
        RetrievalFilters(
            doc_ids=["a"],
            content_types=["application/pdf"],
            uploaded_by=[1],
            uploaded_after=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    assert f is not None
    assert len(f.must) == 4


async def test_search_with_doc_id_filter_excludes_others(vectorstore_factory) -> None:
    async with vectorstore_factory() as store:
        await store.upsert([
            {"vector": [1.0, 0, 0, 0], "payload": {"doc_id": "keep", "content": "x"}},
            {"vector": [0.99, 0, 0, 0], "payload": {"doc_id": "drop", "content": "y"}},
        ])
        results = await store.search(
            query_vector=[1.0, 0, 0, 0],
            top_k=10,
            filters=RetrievalFilters(doc_ids=["keep"]),
        )
        doc_ids = {r["doc_id"] for r in results}
        assert doc_ids == {"keep"}
