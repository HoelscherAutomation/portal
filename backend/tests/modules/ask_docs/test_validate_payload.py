from datetime import datetime

import pytest

import app.database as db_module
from app.modules.ask_docs.models import AskDocsDocument, AskDocsStatus
from scripts.ask_docs_validate_payload import run_validation


@pytest.fixture
async def doc_with_id():
    """Create a real AskDocsDocument and return its UUID as a string."""
    async with db_module.async_session_maker() as session:
        doc = AskDocsDocument(
            filename="x.pdf",
            content_type="application/pdf",
            size_bytes=10,
            uploaded_by=None,
            uploaded_at=datetime(2026, 1, 1),  # naive — matches column type
            status=AskDocsStatus.indexed,
            chunk_count=1,
            storage_path="/tmp/x.pdf",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return str(doc.id)


async def test_validation_passes_on_fully_v2_corpus(doc_with_id, vectorstore_factory):
    async with vectorstore_factory() as store:
        await store.upsert([{
            "vector": [1.0, 0, 0, 0],
            "payload": {
                "doc_id": doc_with_id, "page_num": 1, "chunk_index": 0,
                "content": "x", "source_path": "x.pdf",
                "filename": "x.pdf", "content_type": "application/pdf",
                "uploaded_by": None, "uploaded_at": "2026-01-01T00:00:00Z",
                "payload_schema_version": 2,
            },
        }])
        async with db_module.async_session_maker() as session:
            report = await run_validation(session=session, vectorstore=store)
        assert report["exit_code"] == 0
        assert report["missing_schema_version"] == 0
        assert report["orphan_doc_ids"] == 0


async def test_validation_fails_on_missing_fields(doc_with_id, vectorstore_factory):
    async with vectorstore_factory() as store:
        await store.upsert([{
            "vector": [1.0, 0, 0, 0],
            "payload": {
                "doc_id": doc_with_id, "page_num": 1, "chunk_index": 0,
                "content": "x", "source_path": "x.pdf",
                # Missing all P2.1A fields
            },
        }])
        async with db_module.async_session_maker() as session:
            report = await run_validation(session=session, vectorstore=store)
        assert report["exit_code"] == 1
        assert report["missing_schema_version"] >= 1


async def test_validation_fails_on_orphan(vectorstore_factory):
    """Orphan doc_id (no matching Postgres row) → exit 1."""
    async with vectorstore_factory() as store:
        await store.upsert([{
            "vector": [1.0, 0, 0, 0],
            "payload": {
                "doc_id": "00000000-0000-0000-0000-000000000001",
                "page_num": 1, "chunk_index": 0,
                "content": "x", "source_path": "x.pdf",
                "filename": "x.pdf", "content_type": "application/pdf",
                "uploaded_by": None, "uploaded_at": "2026-01-01T00:00:00Z",
                "payload_schema_version": 2,
            },
        }])
        async with db_module.async_session_maker() as session:
            report = await run_validation(session=session, vectorstore=store)
        assert report["exit_code"] == 1
        assert report["orphan_doc_ids"] == 1


async def test_validation_with_ignore_orphans(vectorstore_factory):
    """--ignore-orphans suppresses the orphan failure but still counts it."""
    async with vectorstore_factory() as store:
        await store.upsert([{
            "vector": [1.0, 0, 0, 0],
            "payload": {
                "doc_id": "00000000-0000-0000-0000-000000000002",
                "page_num": 1, "chunk_index": 0,
                "content": "x", "source_path": "x.pdf",
                "filename": "x.pdf", "content_type": "application/pdf",
                "uploaded_by": None, "uploaded_at": "2026-01-01T00:00:00Z",
                "payload_schema_version": 2,
            },
        }])
        async with db_module.async_session_maker() as session:
            report = await run_validation(
                session=session, vectorstore=store, ignore_orphans=True,
            )
        assert report["exit_code"] == 0
        assert report["orphan_doc_ids"] == 1  # still counted, just not failing


async def test_validation_passes_on_empty_corpus(vectorstore_factory):
    """Validate against a collection with zero points — PASS (no fields missing, no orphans)."""
    async with vectorstore_factory() as store:
        async with db_module.async_session_maker() as session:
            report = await run_validation(session=session, vectorstore=store)
        assert report["exit_code"] == 0
        assert report["scanned"] == 0
        assert report["orphan_doc_ids"] == 0
