"""Retrieval pipeline: query then embed then Qdrant top-K then formatted sources."""
import logging
from typing import Protocol

from app.modules.ask_docs.prompts import FormattedSource
from app.modules.ask_docs.retrieval_types import RetrievalFilters, RetrievalQuery

logger = logging.getLogger(__name__)

_REQUIRED_PAYLOAD_KEYS = ("source_path", "page_num", "content")


class _Embeddings(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    async def aclose(self) -> None: ...


class _Vectorstore(Protocol):
    async def search(
        self,
        *,
        query_vector: list[float],
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[dict]: ...
    async def aclose(self) -> None: ...


async def retrieve_sources(
    *,
    query: RetrievalQuery,
    embeddings: _Embeddings,
    vectorstore: _Vectorstore,
) -> list[FormattedSource]:
    """Embed the query, search Qdrant with optional filters, return formatted sources.

    Drops any chunk with a malformed payload (missing required keys) and logs
    the issue. Returning a synthesized "unknown / page 1 / empty content"
    citation would mask the real bug — better to skip + log so the operator
    sees something happened.
    """
    vector = await embeddings.embed(query.text)
    raw = await vectorstore.search(
        query_vector=vector,
        top_k=query.top_k,
        filters=query.filters,
    )

    sources: list[FormattedSource] = []
    for payload in raw:
        missing = [k for k in _REQUIRED_PAYLOAD_KEYS if k not in payload]
        if missing:
            logger.warning(
                "Qdrant payload missing required keys %s — dropping from results: doc_id=%r chunk_index=%r",
                missing, payload.get("doc_id"), payload.get("chunk_index"),
            )
            continue
        sources.append(FormattedSource(
            number=len(sources) + 1,
            filename=payload["source_path"],
            page_num=payload["page_num"],
            content=payload["content"],
        ))
    return sources
