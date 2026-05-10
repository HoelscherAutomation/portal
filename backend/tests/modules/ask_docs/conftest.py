"""Generate sample PDF/DOCX/TXT files in temp dirs for parser tests."""
from pathlib import Path

import fitz  # pymupdf
import pytest
from docx import Document


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
