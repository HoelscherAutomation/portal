from app.modules.ask_docs.chunker import Chunk, chunk_pages
from app.modules.ask_docs.parsers import ParsedPage


def test_short_text_one_chunk():
    pages = [ParsedPage(page_num=1, text="Hello world.")]
    chunks = chunk_pages(pages, chunk_size_tokens=100, overlap_tokens=10)
    assert len(chunks) == 1
    assert chunks[0].page_num == 1
    assert chunks[0].chunk_index == 0
    assert "Hello world" in chunks[0].text


def test_long_text_splits_into_multiple_chunks():
    long_text = " ".join([f"sentence{i}." for i in range(500)])
    pages = [ParsedPage(page_num=1, text=long_text)]
    chunks = chunk_pages(pages, chunk_size_tokens=100, overlap_tokens=20)
    assert len(chunks) > 1
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_overlap_preserves_context_between_chunks():
    long_text = " ".join([f"word{i}" for i in range(300)])
    pages = [ParsedPage(page_num=1, text=long_text)]
    chunks = chunk_pages(pages, chunk_size_tokens=100, overlap_tokens=20)

    if len(chunks) >= 2:
        tail = chunks[0].text[-50:]
        head = chunks[1].text[:50]
        assert any(w in head for w in tail.split() if len(w) > 3)


def test_multi_page_chunks_track_page_num():
    pages = [
        ParsedPage(page_num=1, text="First page short text."),
        ParsedPage(page_num=2, text="Second page also short."),
        ParsedPage(page_num=3, text="Third page short text too."),
    ]
    chunks = chunk_pages(pages, chunk_size_tokens=100, overlap_tokens=10)
    page_nums = sorted({c.page_num for c in chunks})
    assert page_nums == [1, 2, 3]


def test_empty_pages_skipped():
    pages = [
        ParsedPage(page_num=1, text="real content here"),
        ParsedPage(page_num=2, text="   "),
        ParsedPage(page_num=3, text=""),
    ]
    chunks = chunk_pages(pages, chunk_size_tokens=100, overlap_tokens=10)
    page_nums = {c.page_num for c in chunks}
    assert page_nums == {1}
