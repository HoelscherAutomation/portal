import pytest

from app.modules.ask_docs.embeddings import EmbeddingsClient


class _FakeOllamaResponse:
    def __init__(self, embedding: list[float]):
        self._body = {"embedding": embedding}

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class _FakeHttpClient:
    def __init__(self, embedding: list[float]):
        self._embedding = embedding
        self.calls = []

    async def post(self, url: str, *, json: dict, timeout: float | None = None):
        self.calls.append((url, json))
        return _FakeOllamaResponse(self._embedding)

    async def aclose(self):
        pass


async def test_embeds_text_returns_vector():
    fake = _FakeHttpClient(embedding=[0.1, 0.2, 0.3])
    client = EmbeddingsClient(
        url="http://ollama:11434",
        model="nomic-embed-text",
        http_client=fake,
    )
    vec = await client.embed("hello world")
    assert vec == [0.1, 0.2, 0.3]
    assert len(fake.calls) == 1
    url, body = fake.calls[0]
    assert url == "http://ollama:11434/api/embeddings"
    assert body == {"model": "nomic-embed-text", "prompt": "hello world"}


async def test_embed_batch_returns_list_of_vectors():
    fake = _FakeHttpClient(embedding=[0.5, 0.5])
    client = EmbeddingsClient(
        url="http://ollama:11434",
        model="nomic-embed-text",
        http_client=fake,
    )
    vecs = await client.embed_batch(["one", "two", "three"])
    assert vecs == [[0.5, 0.5], [0.5, 0.5], [0.5, 0.5]]
    assert len(fake.calls) == 3
