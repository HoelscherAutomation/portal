from pathlib import Path

import pytest

from app.modules.ask_docs.parsers import ParsedPage, parse_to_pages


def test_parse_pdf(sample_pdf: Path):
    pages = parse_to_pages(sample_pdf, "application/pdf")
    assert len(pages) == 2
    assert isinstance(pages[0], ParsedPage)
    assert pages[0].page_num == 1
    assert "First page line one" in pages[0].text
    assert pages[1].page_num == 2
    assert "Second page text" in pages[1].text


def test_parse_docx(sample_docx: Path):
    pages = parse_to_pages(sample_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert len(pages) == 1
    assert pages[0].page_num == 1
    assert "Paragraph one" in pages[0].text
    assert "Paragraph three" in pages[0].text


def test_parse_txt(sample_txt: Path):
    pages = parse_to_pages(sample_txt, "text/plain")
    assert len(pages) == 1
    assert "Line one" in pages[0].text


def test_parse_md(sample_md: Path):
    pages = parse_to_pages(sample_md, "text/markdown")
    assert len(pages) == 1
    assert "Heading" in pages[0].text


def test_parse_unknown_content_type_raises():
    with pytest.raises(ValueError, match="Unsupported content type"):
        parse_to_pages(Path("/tmp/whatever.xyz"), "application/x-weird")


def test_parse_corrupt_pdf_raises_parser_error(tmp_path: Path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf")
    from app.modules.ask_docs.parsers import ParserError
    with pytest.raises(ParserError):
        parse_to_pages(bad, "application/pdf")
