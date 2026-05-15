from datetime import datetime

import pytest

import app.database as db_module
from app.modules.ask_docs.models import AskDocsDocument, AskDocsStatus
from scripts.ask_docs_backfill_payload import run_backfill


@pytest.fixture
async def seeded_doc():
    """Create a single indexed AskDocsDocument and yield its id."""
    async with db_module.async_session_maker() as session:
        doc = AskDocsDocument(
            filename="legacy.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            uploaded_by=None,
            # Column is TIMESTAMP WITHOUT TIME ZONE; use a naive datetime.
            uploaded_at=datetime(2026, 4, 1, 0, 0, 0),
            status=AskDocsStatus.indexed,
            chunk_count=2,
            storage_path="/tmp/legacy.pdf",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return doc


async def test_backfill_updates_all_pre_v2_points(seeded_doc, vectorstore_factory):
    async with vectorstore_factory() as store:
        await store.upsert([
            {"vector": [1.0, 0, 0, 0], "payload": {
                "doc_id": str(seeded_doc.id), "page_num": 1, "chunk_index": 0,
                "content": "hello", "source_path": "legacy.pdf",
            }},
            {"vector": [0, 1.0, 0, 0], "payload": {
                "doc_id": str(seeded_doc.id), "page_num": 1, "chunk_index": 1,
                "content": "world", "source_path": "legacy.pdf",
            }},
        ])
        async with db_module.async_session_maker() as session:
            counters = await run_backfill(session=session, vectorstore=store, batch_size=100)
        assert counters["scanned"] == 2
        assert counters["updated"] == 2
        assert counters["skipped_already_v2"] == 0


async def test_backfill_is_idempotent(seeded_doc, vectorstore_factory):
    async with vectorstore_factory() as store:
        await store.upsert([
            {"vector": [1.0, 0, 0, 0], "payload": {
                "doc_id": str(seeded_doc.id), "page_num": 1, "chunk_index": 0,
                "content": "hello", "source_path": "legacy.pdf",
            }},
        ])
        async with db_module.async_session_maker() as session:
            await run_backfill(session=session, vectorstore=store, batch_size=100)
        async with db_module.async_session_maker() as session:
            counters = await run_backfill(session=session, vectorstore=store, batch_size=100)
        assert counters["updated"] == 0
        assert counters["skipped_already_v2"] == 1


async def test_backfill_skips_orphan_chunks(vectorstore_factory):
    async with vectorstore_factory() as store:
        await store.upsert([
            {"vector": [1.0, 0, 0, 0], "payload": {
                "doc_id": "00000000-0000-0000-0000-000000000001",
                "page_num": 1, "chunk_index": 0,
                "content": "x", "source_path": "ghost.pdf",
            }},
        ])
        async with db_module.async_session_maker() as session:
            counters = await run_backfill(session=session, vectorstore=store, batch_size=100)
        assert counters["scanned"] == 1
        assert counters["updated"] == 0
        assert counters["skipped_missing_doc"] == 1


async def test_backfill_resumes_from_saved_offset(seeded_doc, vectorstore_factory):
    """Stop after one batch, then re-run; resume must continue from where it stopped."""
    async with vectorstore_factory() as store:
        # 7 total points so batch_size=2 forces multiple iterations
        points = [
            {"vector": [0, 0, 0, 1.0 - i * 0.001], "payload": {
                "doc_id": str(seeded_doc.id), "page_num": 1, "chunk_index": i,
                "content": f"chunk{i}", "source_path": "legacy.pdf",
            }}
            for i in range(7)
        ]
        await store.upsert(points)

        async with db_module.async_session_maker() as session:
            counters = await run_backfill(
                session=session, vectorstore=store, batch_size=2, max_batches=1,
            )
        assert counters["updated"] == 2

        async with db_module.async_session_maker() as session:
            counters = await run_backfill(session=session, vectorstore=store, batch_size=2)
        # Remaining 5 points should be updated on the second run
        assert counters["updated"] == 5
        # Strict check: second run only scans the remainder, proving the saved offset was loaded
        assert counters["scanned"] == 5
        assert counters["skipped_already_v2"] == 0
