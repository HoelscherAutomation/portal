"""Qdrant client wrapper for Ask Docs vector storage."""
import uuid as _uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels


class VectorStore:
    def __init__(
        self,
        *,
        url: str,
        collection_name: str,
        vector_size: int = 768,
    ):
        self._url = url
        self._collection = collection_name
        self._vector_size = vector_size
        self._client: AsyncQdrantClient | None = None

    def _get_client(self) -> AsyncQdrantClient:
        """Lazily construct the underlying client.

        AsyncQdrantClient creates an httpx.AsyncClient (with internal asyncio
        primitives) at construction time. Constructing it lazily on first use
        binds those primitives to the running event loop, which avoids
        cross-loop binding errors in pytest fixtures and worker startup.
        """
        if self._client is None:
            self._client = AsyncQdrantClient(url=self._url)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._get_client().close()
            self._client = None

    async def ensure_collection(self) -> None:
        """Create the collection if it doesn't exist."""
        existing = await self._get_client().get_collections()
        if self._collection in [c.name for c in existing.collections]:
            return
        await self._get_client().create_collection(
            collection_name=self._collection,
            vectors_config=qmodels.VectorParams(
                size=self._vector_size,
                distance=qmodels.Distance.COSINE,
            ),
        )

    async def delete_all(self) -> None:
        """Delete every point in the collection. For tests."""
        await self._get_client().delete(
            collection_name=self._collection,
            points_selector=qmodels.FilterSelector(filter=qmodels.Filter(must=[])),
        )

    async def upsert(self, points: list[dict]) -> None:
        """Insert/update points. Each point: {vector, payload}."""
        qpoints = [
            qmodels.PointStruct(
                id=str(_uuid.uuid4()),
                vector=p["vector"],
                payload=p["payload"],
            )
            for p in points
        ]
        await self._get_client().upsert(collection_name=self._collection, points=qpoints)

    async def search(self, *, query_vector: list[float], top_k: int = 8) -> list[dict]:
        """Return top_k payloads ordered by cosine similarity."""
        results = await self._get_client().search(
            collection_name=self._collection,
            query_vector=query_vector,
            limit=top_k,
        )
        return [r.payload for r in results]

    async def delete_by_doc_id(self, doc_id: str) -> None:
        """Remove all chunks belonging to a document."""
        await self._get_client().delete(
            collection_name=self._collection,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="doc_id",
                            match=qmodels.MatchValue(value=doc_id),
                        )
                    ]
                )
            ),
        )
