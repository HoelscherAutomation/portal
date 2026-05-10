"""Retrieval pipeline: query → embed → Qdrant top-K → formatted sources."""
from typing import Protocol

from app.modules.ask_docs.prompts import FormattedSource


class _Embeddings(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    async def aclose(self) -> None: ...


class _Vectorstore(Protocol):
    async def search(self, *, query_vector: list[float], top_k: int) -> list[dict]: ...
    async def aclose(self) -> None: ...


async def retrieve_sources(
    *,
    query: str,
    top_k: int,
    embeddings: _Embeddings,
    vectorstore: _Vectorstore,
) -> list[FormattedSource]:
    """Embed the query, search Qdrant, return formatted sources (1-indexed numbering)."""
    vector = await embeddings.embed(query)
    raw = await vectorstore.search(query_vector=vector, top_k=top_k)
    return [
        FormattedSource(
            number=i + 1,
            filename=payload.get("source_path", "unknown"),
            page_num=payload.get("page_num", 1),
            content=payload.get("content", ""),
        )
        for i, payload in enumerate(raw)
    ]
