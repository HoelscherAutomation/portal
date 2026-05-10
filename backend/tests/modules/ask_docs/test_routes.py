import io
from pathlib import Path

import fitz
import pytest
from httpx import AsyncClient

import app.database as db_module
from tests.test_auth import _create_user


async def _login(client: AsyncClient, email: str = "admin@example.com") -> None:
    await _create_user(email, "test-password-123", superuser=True)
    response = await client.post(
        "/api/auth/login",
        data={"username": email, "password": "test-password-123"},
    )
    assert response.status_code in (200, 204)


def _make_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello world.")
    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


async def test_upload_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/modules/ask-docs/documents",
        files={"file": ("test.pdf", _make_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 401


async def test_upload_creates_pending_document(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.modules.ask_docs.routes._enqueue_index",
        lambda doc_id: None,
    )

    await _login(client)
    response = await client.post(
        "/api/modules/ask-docs/documents",
        files={"file": ("test.pdf", _make_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["filename"] == "test.pdf"
    assert body["status"] == "pending"
    assert body["chunk_count"] == 0


async def test_list_documents_returns_uploaded(client: AsyncClient, monkeypatch):
    monkeypatch.setattr("app.modules.ask_docs.routes._enqueue_index", lambda doc_id: None)
    await _login(client)
    await client.post(
        "/api/modules/ask-docs/documents",
        files={"file": ("a.pdf", _make_pdf_bytes(), "application/pdf")},
    )
    await client.post(
        "/api/modules/ask-docs/documents",
        files={"file": ("b.pdf", _make_pdf_bytes(), "application/pdf")},
    )

    response = await client.get("/api/modules/ask-docs/documents")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    filenames = {d["filename"] for d in body}
    assert filenames == {"a.pdf", "b.pdf"}


async def test_get_document_by_id(client: AsyncClient, monkeypatch):
    monkeypatch.setattr("app.modules.ask_docs.routes._enqueue_index", lambda doc_id: None)
    await _login(client)
    create = await client.post(
        "/api/modules/ask-docs/documents",
        files={"file": ("x.pdf", _make_pdf_bytes(), "application/pdf")},
    )
    doc_id = create.json()["id"]

    response = await client.get(f"/api/modules/ask-docs/documents/{doc_id}")
    assert response.status_code == 200
    assert response.json()["filename"] == "x.pdf"


async def test_delete_document(client: AsyncClient, monkeypatch):
    monkeypatch.setattr("app.modules.ask_docs.routes._enqueue_index", lambda doc_id: None)
    monkeypatch.setattr("app.modules.ask_docs.routes._enqueue_delete", lambda doc_id: None)
    await _login(client)
    create = await client.post(
        "/api/modules/ask-docs/documents",
        files={"file": ("doomed.pdf", _make_pdf_bytes(), "application/pdf")},
    )
    doc_id = create.json()["id"]

    delete = await client.delete(f"/api/modules/ask-docs/documents/{doc_id}")
    assert delete.status_code == 204

    get = await client.get(f"/api/modules/ask-docs/documents/{doc_id}")
    assert get.status_code == 404


async def test_upload_rejects_unsupported_content_type(client: AsyncClient):
    await _login(client)
    response = await client.post(
        "/api/modules/ask-docs/documents",
        files={"file": ("ouput.xls", b"binary stuff", "application/vnd.ms-excel")},
    )
    assert response.status_code == 400
