"""Generate sample PDF/DOCX/TXT files in temp dirs for parser tests."""
from contextlib import asynccontextmanager
from pathlib import Path

import fitz  # pymupdf
import pytest
from docx import Document

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


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """A 2-page PDF with known text content."""
    target = tmp_path / "sample.pdf"
    doc = fitz.open()

    page1 = doc.new_page()
    page1.insert_text((72, 72), "First page line one.\nFirst page line two.")

    page2 = doc.new_page()
    page2.insert_text((72, 72), "Second page text here.")

    doc.save(str(target))
    doc.close()
    return target


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    """A DOCX with three paragraphs."""
    target = tmp_path / "sample.docx"
    doc = Document()
    doc.add_paragraph("Paragraph one.")
    doc.add_paragraph("Paragraph two.")
    doc.add_paragraph("Paragraph three.")
    doc.save(str(target))
    return target


@pytest.fixture
def sample_txt(tmp_path: Path) -> Path:
    target = tmp_path / "sample.txt"
    target.write_text("Line one.\nLine two.\nLine three.\n", encoding="utf-8")
    return target


@pytest.fixture
def sample_md(tmp_path: Path) -> Path:
    target = tmp_path / "sample.md"
    target.write_text("# Heading\n\nSome paragraph text here.\n", encoding="utf-8")
    return target
