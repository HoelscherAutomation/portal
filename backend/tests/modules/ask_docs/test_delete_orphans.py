from datetime import datetime

import pytest

import app.database as db_module
from app.modules.ask_docs.models import AskDocsDocument, AskDocsStatus
from scripts.ask_docs_delete_orphans import find_and_delete_orphans


@pytest.fixture
async def live_doc_id():
    """Create a real AskDocsDocument and return its UUID string."""
    async with db_module.async_session_maker() as session:
        doc = AskDocsDocument(
            filename="live.pdf",
            content_type="application/pdf",
            size_bytes=10,
            uploaded_by=None,
            uploaded_at=datetime(2026, 1, 1),  # naive
            status=AskDocsStatus.indexed,
            chunk_count=1,
            storage_path="/tmp/live.pdf",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return str(doc.id)


async def test_delete_orphans_removes_only_orphan_points(live_doc_id, vectorstore_factory):
    async with vectorstore_factory() as store:
        await store.upsert([
            {"vector": [1.0, 0, 0, 0], "payload": {
                "doc_id": live_doc_id, "page_num": 1, "chunk_index": 0,
                "content": "live", "source_path": "live.pdf",
            }},
            {"vector": [0, 1.0, 0, 0], "payload": {
                "doc_id": "00000000-0000-0000-0000-000000000003",
                "page_num": 1, "chunk_index": 0,
                "content": "ghost", "source_path": "ghost.pdf",
            }},
        ])
        async with db_module.async_session_maker() as session:
            result = await find_and_delete_orphans(
                session=session, vectorstore=store, confirm=True,
            )
        assert result["deleted_doc_ids"] == ["00000000-0000-0000-0000-000000000003"]
        assert result["dry_run"] is False

        # Live doc's chunks remain; orphan's chunks gone
        remaining = await store.search(query_vector=[1.0, 0, 0, 0], top_k=10)
        doc_ids = {p["doc_id"] for p in remaining}
        assert live_doc_id in doc_ids
        assert "00000000-0000-0000-0000-000000000003" not in doc_ids


async def test_delete_orphans_dry_run_does_nothing(vectorstore_factory):
    """confirm=False is the default safety mode — list orphans but don't touch Qdrant."""
    async with vectorstore_factory() as store:
        await store.upsert([{
            "vector": [1.0, 0, 0, 0],
            "payload": {
                "doc_id": "00000000-0000-0000-0000-000000000004",
                "page_num": 1, "chunk_index": 0,
                "content": "x", "source_path": "x.pdf",
            },
        }])
        async with db_module.async_session_maker() as session:
            result = await find_and_delete_orphans(
                session=session, vectorstore=store, confirm=False,
            )
        assert result["dry_run"] is True
        assert "00000000-0000-0000-0000-000000000004" in result["orphan_doc_ids"]
        assert result["deleted_doc_ids"] == []

        # Point still present
        remaining = await store.search(query_vector=[1.0, 0, 0, 0], top_k=10)
        assert any(p["doc_id"] == "00000000-0000-0000-0000-000000000004" for p in remaining)


async def test_delete_orphans_no_orphans_returns_empty_lists(live_doc_id, vectorstore_factory):
    """All chunks have valid doc_ids — nothing to delete."""
    async with vectorstore_factory() as store:
        await store.upsert([{
            "vector": [1.0, 0, 0, 0],
            "payload": {
                "doc_id": live_doc_id, "page_num": 1, "chunk_index": 0,
                "content": "x", "source_path": "live.pdf",
            },
        }])
        async with db_module.async_session_maker() as session:
            result = await find_and_delete_orphans(
                session=session, vectorstore=store, confirm=True,
            )
        assert result["orphan_doc_ids"] == []
        assert result["deleted_doc_ids"] == []
