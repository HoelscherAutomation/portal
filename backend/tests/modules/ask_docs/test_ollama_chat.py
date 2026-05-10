from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.ask_docs.ollama_chat import OllamaChatClient


def _make_fake_client(chunks: list[dict]):
    """ollama.AsyncClient.chat() with stream=True returns an async iterator of dicts."""

    async def _ait():
        for c in chunks:
            yield c

    fake = MagicMock()
    # The wrapper does `await self._client.chat(...)` then iterates the result.
    # We mimic that with AsyncMock(return_value=_ait()) — the awaited result is the async iterator.
    fake.chat = AsyncMock(return_value=_ait())
    return fake


async def test_stream_chat_yields_text_deltas():
    fake = _make_fake_client([
        {"message": {"content": "Hel"}, "done": False},
        {"message": {"content": "lo "}, "done": False},
        {"message": {"content": "world."}, "done": False},
        {"done": True, "prompt_eval_count": 12, "eval_count": 3, "message": {"content": ""}},
    ])
    client = OllamaChatClient(url="http://x", model="llama3.1:8b", client=fake)

    out = []
    async for delta in client.stream_chat(system="sys", user="hi", max_tokens=100):
        out.append(delta)

    assert "".join(out) == "Hello world."


async def test_stream_chat_invokes_on_final_usage():
    fake = _make_fake_client([
        {"message": {"content": "abc"}, "done": False},
        {"done": True, "prompt_eval_count": 50, "eval_count": 10, "message": {"content": ""}},
    ])
    client = OllamaChatClient(url="http://x", model="llama3.1:8b", client=fake)

    usage = {}
    async for _ in client.stream_chat(system="s", user="u", max_tokens=64, on_final_usage=usage.update):
        pass

    assert usage == {"input_tokens": 50, "output_tokens": 10}


async def test_stream_chat_passes_system_user_and_options():
    fake = _make_fake_client([{"done": True, "message": {"content": ""}}])
    client = OllamaChatClient(url="http://x", model="llama3.1:8b", client=fake)

    async for _ in client.stream_chat(system="my system", user="my user", max_tokens=512):
        pass

    fake.chat.assert_awaited_once()
    call = fake.chat.call_args.kwargs
    assert call["model"] == "llama3.1:8b"
    assert call["stream"] is True
    assert call["messages"] == [
        {"role": "system", "content": "my system"},
        {"role": "user", "content": "my user"},
    ]
    assert call["options"] == {"num_predict": 512}
