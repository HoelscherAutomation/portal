from pathlib import Path

import fitz
import pytest
from sqlalchemy import select

import app.database as db_module
from app.models import AskDocsDocument, User
from app.modules.ask_docs.models import AskDocsStatus
from app.modules.ask_docs.tasks import index_document
from tests.test_auth import _create_user


@pytest.fixture
async def pending_doc(tmp_path: Path):
    """Create a pending AskDocsDocument with a real small PDF on disk."""
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Quick brown fox jumps over the lazy dog. " * 10)
    doc.save(str(pdf_path))
    doc.close()

    async with db_module.async_session_maker() as session:
        document = AskDocsDocument(
            filename="test.pdf",
            content_type="application/pdf",
            size_bytes=pdf_path.stat().st_size,
            uploaded_by=None,
            status=AskDocsStatus.pending,
            chunk_count=0,
            storage_path=str(pdf_path),
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        return document


async def test_index_document_marks_indexed_with_chunks(pending_doc: AskDocsDocument, monkeypatch):
    captured_points = []

    class FakeStore:
        async def ensure_collection(self):
            pass

        async def upsert(self, points):
            captured_points.extend(points)

        async def aclose(self):
            pass

    class FakeEmb:
        async def embed_batch(self, texts):
            return [[0.1] * 768 for _ in texts]

        async def aclose(self):
            pass

    fake_store = FakeStore()
    fake_emb = FakeEmb()
    monkeypatch.setattr("app.modules.ask_docs.tasks._make_embeddings_client", lambda: fake_emb)
    monkeypatch.setattr("app.modules.ask_docs.tasks._make_vectorstore", lambda: fake_store)

    await index_document({"redis": None}, str(pending_doc.id))

    async with db_module.async_session_maker() as session:
        refreshed = await session.get(AskDocsDocument, pending_doc.id)
        assert refreshed.status == AskDocsStatus.indexed
        assert refreshed.chunk_count > 0
        assert refreshed.error_message is None

    assert len(captured_points) > 0
    assert all("doc_id" in p["payload"] for p in captured_points)


async def test_index_document_writes_p2_1a_payload_fields(pending_doc: AskDocsDocument, monkeypatch):
    """P2.1A: ingest writes filename/content_type/uploaded_by/uploaded_at/version to payload."""
    captured_points = []

    class FakeStore:
        async def ensure_collection(self):
            pass

        async def upsert(self, points):
            captured_points.extend(points)

        async def aclose(self):
            pass

    class FakeEmb:
        async def embed_batch(self, texts):
            return [[0.1] * 768 for _ in texts]

        async def aclose(self):
            pass

    fake_store = FakeStore()
    fake_emb = FakeEmb()
    monkeypatch.setattr("app.modules.ask_docs.tasks._make_embeddings_client", lambda: fake_emb)
    monkeypatch.setattr("app.modules.ask_docs.tasks._make_vectorstore", lambda: fake_store)

    await index_document({"redis": None}, str(pending_doc.id))

    assert len(captured_points) > 0
    for point in captured_points:
        payload = point["payload"]
        assert payload["filename"] == "test.pdf"
        assert payload["content_type"] == "application/pdf"
        assert payload["uploaded_by"] is None
        assert "uploaded_at" in payload
        assert isinstance(payload["uploaded_at"], str)
        assert payload["payload_schema_version"] == 2


async def test_index_document_writes_uploaded_by_int_when_set(tmp_path: Path, monkeypatch):
    """P2.1A: payload['uploaded_by'] is a real int (not str/missing) when doc has an uploader."""
    # Create a real user to satisfy the FK (AskDocsDocument.uploaded_by → users.id).
    await _create_user("uploader@example.com", "test-password-123")
    async with db_module.async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == "uploader@example.com"))
        user = result.scalar_one()
        user_id = user.id

    pdf_path = tmp_path / "owned.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Quick brown fox jumps over the lazy dog. " * 10)
    doc.save(str(pdf_path))
    doc.close()

    async with db_module.async_session_maker() as session:
        document = AskDocsDocument(
            filename="owned.pdf",
            content_type="application/pdf",
            size_bytes=pdf_path.stat().st_size,
            uploaded_by=user_id,
            status=AskDocsStatus.pending,
            chunk_count=0,
            storage_path=str(pdf_path),
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        doc_id = document.id

    captured_points = []

    class FakeStore:
        async def ensure_collection(self):
            pass

        async def upsert(self, points):
            captured_points.extend(points)

        async def aclose(self):
            pass

    class FakeEmb:
        async def embed_batch(self, texts):
            return [[0.1] * 768 for _ in texts]

        async def aclose(self):
            pass

    fake_store = FakeStore()
    fake_emb = FakeEmb()
    monkeypatch.setattr("app.modules.ask_docs.tasks._make_embeddings_client", lambda: fake_emb)
    monkeypatch.setattr("app.modules.ask_docs.tasks._make_vectorstore", lambda: fake_store)

    await index_document({"redis": None}, str(doc_id))

    assert len(captured_points) > 0
    for point in captured_points:
        payload = point["payload"]
        # Regression guard: must be the exact int FK, not a stringified id or missing.
        assert payload["uploaded_by"] == user_id
        assert isinstance(payload["uploaded_by"], int)


async def test_index_document_marks_failed_on_corrupt_file(tmp_path: Path):
    bad_path = tmp_path / "bad.pdf"
    bad_path.write_bytes(b"not a pdf")

    async with db_module.async_session_maker() as session:
        doc = AskDocsDocument(
            filename="bad.pdf",
            content_type="application/pdf",
            size_bytes=10,
            uploaded_by=None,
            status=AskDocsStatus.pending,
            chunk_count=0,
            storage_path=str(bad_path),
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        doc_id = doc.id

    await index_document({"redis": None}, str(doc_id))

    async with db_module.async_session_maker() as session:
        refreshed = await session.get(AskDocsDocument, doc_id)
        assert refreshed.status == AskDocsStatus.failed
        assert refreshed.error_message is not None
        assert "PDF" in refreshed.error_message or "parse" in refreshed.error_message.lower()
