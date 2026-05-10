"""Anthropic chat client wrapper. Streams text deltas; reports final token usage."""
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)


class AnthropicChatClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: Any | None = None,
    ):
        self._model = model
        self._client = client or AsyncAnthropic(api_key=api_key)

    async def stream_chat(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        on_final_usage: Callable[[dict], None] | None = None,
    ) -> AsyncIterator[str]:
        """Stream text deltas from Anthropic. Calls on_final_usage with token counts when done."""
        async with self._client.messages.stream(
            model=self._model,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=max_tokens,
        ) as stream:
            async for delta in stream.text_stream:
                yield delta
            if on_final_usage is not None:
                final = await stream.get_final_message()
                on_final_usage({
                    "input_tokens": final.usage.input_tokens,
                    "output_tokens": final.usage.output_tokens,
                })
