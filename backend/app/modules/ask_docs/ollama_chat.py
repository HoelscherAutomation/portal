"""Ollama chat client wrapper. Streams /api/chat NDJSON; reports final token usage.

Same interface contract as AnthropicChatClient (see chat_client.ChatClient Protocol).
"""
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from ollama import AsyncClient

logger = logging.getLogger(__name__)


class OllamaChatClient:
    def __init__(
        self,
        *,
        url: str,
        model: str,
        client: Any | None = None,
    ):
        self._model = model
        self._client = client or AsyncClient(host=url)

    async def stream_chat(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        on_final_usage: Callable[[dict], None] | None = None,
    ) -> AsyncIterator[str]:
        stream = await self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
            options={"num_predict": max_tokens},
        )

        last_chunk: dict | None = None
        async for chunk in stream:
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content
            last_chunk = chunk

        if on_final_usage and last_chunk and last_chunk.get("done"):
            on_final_usage({
                "input_tokens": last_chunk.get("prompt_eval_count", 0),
                "output_tokens": last_chunk.get("eval_count", 0),
            })

    async def aclose(self) -> None:
        """Best-effort close — ollama.AsyncClient holds an httpx connection pool."""
        client_inner = getattr(self._client, "_client", None)
        if client_inner is not None:
            try:
                await client_inner.aclose()
            except Exception:
                logger.exception("Failed to close OllamaChatClient httpx pool")
