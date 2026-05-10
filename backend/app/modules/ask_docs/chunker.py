"""Token-based sliding-window chunker.

Chunks are produced per page (so each chunk's page_num is meaningful).
For pages longer than chunk_size_tokens, multiple chunks are emitted with
overlap_tokens of overlap between consecutive chunks.
"""
from dataclasses import dataclass

import tiktoken

from app.modules.ask_docs.parsers import ParsedPage

# cl100k_base is GPT-4's encoding — close enough to Claude tokenization for
# chunk-size purposes (we just need consistent counts).
_encoder = tiktoken.get_encoding("cl100k_base")


@dataclass(frozen=True)
class Chunk:
    page_num: int
    chunk_index: int  # 0-indexed across all chunks of the document
    text: str


def chunk_pages(
    pages: list[ParsedPage],
    *,
    chunk_size_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    """Split pages into overlapping chunks.

    Within each page: if shorter than chunk_size, emit one chunk; otherwise
    sliding window. Chunk indices are global (continue across pages).
    """
    chunks: list[Chunk] = []
    chunk_index = 0
    step = chunk_size_tokens - overlap_tokens
    if step <= 0:
        raise ValueError("overlap_tokens must be less than chunk_size_tokens")

    for page in pages:
        if not page.text.strip():
            continue

        tokens = _encoder.encode(page.text)
        if len(tokens) <= chunk_size_tokens:
            chunks.append(Chunk(
                page_num=page.page_num,
                chunk_index=chunk_index,
                text=page.text,
            ))
            chunk_index += 1
            continue

        start = 0
        while start < len(tokens):
            end = min(start + chunk_size_tokens, len(tokens))
            window = tokens[start:end]
            text = _encoder.decode(window)
            chunks.append(Chunk(
                page_num=page.page_num,
                chunk_index=chunk_index,
                text=text,
            ))
            chunk_index += 1
            if end == len(tokens):
                break
            start += step

    return chunks
