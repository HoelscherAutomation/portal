from unittest.mock import AsyncMock

import pytest

from app.modules.ask_docs.llm import AnthropicChatClient


class _FakeStream:
    """Mimics Anthropic's streaming response context manager."""
    def __init__(self, deltas: list[str], usage_input: int = 100, usage_output: int = 50):
        self._deltas = deltas
        self._usage = type("Usage", (), {"input_tokens": usage_input, "output_tokens": usage_output})()
        self.text_stream = self._make_text_stream()

    async def _make_text_stream(self):
        for d in self._deltas:
            yield d

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get_final_message(self):
        return type("FinalMessage", (), {"usage": self._usage})()


class _FakeMessages:
    def __init__(self, deltas: list[str]):
        self._deltas = deltas
        self.last_call = None

    def stream(self, **kwargs):
        self.last_call = kwargs
        return _FakeStream(self._deltas)


class _FakeClient:
    def __init__(self, deltas: list[str]):
        self.messages = _FakeMessages(deltas)


async def test_stream_chat_yields_text_deltas():
    fake = _FakeClient(deltas=["Hel", "lo ", "world."])
    client = AnthropicChatClient(api_key="sk-test", model="claude-sonnet-4-6", client=fake)

    out = []
    async for delta in client.stream_chat(system="sys", user="hi", max_tokens=100):
        out.append(delta)

    assert "".join(out) == "Hello world."


async def test_stream_chat_passes_system_and_user():
    fake = _FakeClient(deltas=["x"])
    client = AnthropicChatClient(api_key="sk-test", model="claude-sonnet-4-6", client=fake)

    async for _ in client.stream_chat(system="my system", user="my user", max_tokens=999):
        pass

    call = fake.messages.last_call
    assert call["model"] == "claude-sonnet-4-6"
    assert call["system"] == "my system"
    assert call["max_tokens"] == 999
    assert call["messages"] == [{"role": "user", "content": "my user"}]


async def test_get_final_usage_after_stream():
    fake = _FakeClient(deltas=["abc"])
    client = AnthropicChatClient(api_key="sk-test", model="claude-sonnet-4-6", client=fake)

    final_usage = {}
    async for _ in client.stream_chat(system="s", user="u", max_tokens=100, on_final_usage=final_usage.update):
        pass

    assert final_usage == {"input_tokens": 100, "output_tokens": 50}
