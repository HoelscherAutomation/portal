"""Document → text-with-page-numbers extraction.

One ParsedPage per source page (PDFs) or one page total for formats without
real pagination (DOCX/TXT/MD).
"""
from dataclasses import dataclass
from pathlib import Path

import fitz  # pymupdf
from docx import Document


class ParserError(Exception):
    """Raised when a document cannot be parsed."""


@dataclass(frozen=True)
class ParsedPage:
    page_num: int  # 1-indexed
    text: str


_PDF_TYPES = {"application/pdf"}
_DOCX_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_PLAINTEXT_TYPES = {"text/plain", "text/markdown"}


def parse_to_pages(path: Path, content_type: str) -> list[ParsedPage]:
    """Parse the document and return its text broken into pages.

    Raises ValueError for unsupported content types and ParserError for
    parse failures (corrupt/encrypted/unreadable files).
    """
    if content_type in _PDF_TYPES:
        return _parse_pdf(path)
    if content_type in _DOCX_TYPES:
        return _parse_docx(path)
    if content_type in _PLAINTEXT_TYPES:
        return _parse_plaintext(path)
    raise ValueError(f"Unsupported content type: {content_type}")


def _parse_pdf(path: Path) -> list[ParsedPage]:
    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise ParserError(f"Failed to open PDF: {exc}") from exc

    pages: list[ParsedPage] = []
    try:
        for i, page in enumerate(doc, start=1):
            text = page.get_text()
            if text.strip():
                pages.append(ParsedPage(page_num=i, text=text))
    finally:
        doc.close()

    if not pages:
        raise ParserError("PDF contained no extractable text (may be scanned/image-only)")
    return pages


def _parse_docx(path: Path) -> list[ParsedPage]:
    try:
        doc = Document(str(path))
    except Exception as exc:
        raise ParserError(f"Failed to open DOCX: {exc}") from exc

    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    if not paragraphs:
        raise ParserError("DOCX contained no text")
    return [ParsedPage(page_num=1, text="\n\n".join(paragraphs))]


def _parse_plaintext(path: Path) -> list[ParsedPage]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ParserError(f"File is not valid UTF-8: {exc}") from exc

    if not text.strip():
        raise ParserError("File is empty")
    return [ParsedPage(page_num=1, text=text)]
