"""Ollama embeddings client wrapper.

Talks to a running Ollama server over HTTP. Default model: nomic-embed-text.
"""
import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class _AsyncHttpPost(Protocol):
    async def post(self, url: str, *, json: dict, timeout: float | None = ...): ...
    async def aclose(self) -> None: ...


class EmbeddingsClient:
    def __init__(
        self,
        *,
        url: str,
        model: str,
        http_client: _AsyncHttpPost | None = None,
    ):
        self._url = url.rstrip("/")
        self._model = model
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0))

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def embed(self, text: str) -> list[float]:
        """Return a single embedding vector for one text input."""
        response = await self._http.post(
            f"{self._url}/api/embeddings",
            json={"model": self._model, "prompt": text},
            timeout=30.0,
        )
        response.raise_for_status()
        body = response.json()
        return body["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed many texts. Ollama doesn't batch natively — sequential calls."""
        results: list[list[float]] = []
        for text in texts:
            results.append(await self.embed(text))
        return results
