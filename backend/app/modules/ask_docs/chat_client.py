"""Common interface implemented by AnthropicChatClient and OllamaChatClient."""
from collections.abc import AsyncIterator, Callable
from typing import Protocol


class ChatClient(Protocol):
    """Streaming chat client. Yields text deltas; reports final token usage on completion."""

    async def stream_chat(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        on_final_usage: Callable[[dict], None] | None = None,
    ) -> AsyncIterator[str]: ...
