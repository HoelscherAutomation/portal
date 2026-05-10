import pytest
from fastapi import HTTPException

from app.modules._config_service import save_config
from app.modules.ask_docs.llm import AnthropicChatClient
from app.modules.ask_docs.llm_factory import make_llm_client
from app.modules.ask_docs.ollama_chat import OllamaChatClient


def _settings_obj(*, anthropic_key=None):
    """Build a minimal settings stand-in matching the fields llm_factory reads."""
    return type("S", (), {
        "anthropic_api_key": anthropic_key,
        "anthropic_model": "claude-sonnet-4-6",
        "ollama_url": "http://ollama:11434",
        "ask_docs_top_k": 8,
        "ask_docs_max_answer_tokens": 1024,
        "secret_key": "test-secret-key-32-bytes-of-data!",
        "ask_docs_embedding_model": "nomic-embed-text",
        "qdrant_url": "http://qdrant:6333",
    })()


def _ask_docs_payload(**overrides) -> dict:
    base = {
        "llm_mode": "anthropic",
        "anthropic": {"api_key": None, "model": "claude-sonnet-4-6", "max_tokens": 1024},
        "ollama": {"url": "", "model": "", "max_tokens": 1024},
        "hoelscher_proxy": {},
    }
    for k, v in overrides.items():
        base[k] = v
    return base


async def test_anthropic_mode_with_db_key_uses_db_key(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: _settings_obj(anthropic_key=None))
    await save_config("ask-docs", _ask_docs_payload(anthropic={
        "api_key": "sk-from-db", "model": "claude-sonnet-4-6", "max_tokens": 1024,
    }), updated_by=None)

    client, mode = await make_llm_client()
    assert isinstance(client, AnthropicChatClient)
    assert mode == "anthropic"
    assert client._model == "claude-sonnet-4-6"


async def test_anthropic_mode_no_db_key_falls_back_to_env(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: _settings_obj(anthropic_key="sk-from-env"))
    # No save_config call → DB empty → defaults (anthropic mode, no key)
    client, mode = await make_llm_client()
    assert isinstance(client, AnthropicChatClient)
    assert mode == "anthropic"


async def test_anthropic_mode_no_db_no_env_raises_503(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: _settings_obj(anthropic_key=None))
    with pytest.raises(HTTPException) as exc:
        await make_llm_client()
    assert exc.value.status_code == 503


async def test_ollama_mode_uses_db_settings(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: _settings_obj(anthropic_key=None))
    await save_config("ask-docs", _ask_docs_payload(
        llm_mode="ollama",
        ollama={"url": "http://192.168.10.50:11434", "model": "llama3.1:8b", "max_tokens": 1024},
    ), updated_by=None)

    client, mode = await make_llm_client()
    assert isinstance(client, OllamaChatClient)
    assert mode == "ollama"
    assert client._model == "llama3.1:8b"


async def test_hoelscher_proxy_mode_raises_503(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: _settings_obj(anthropic_key=None))
    await save_config("ask-docs", _ask_docs_payload(llm_mode="hoelscher_proxy"), updated_by=None)
    with pytest.raises(HTTPException) as exc:
        await make_llm_client()
    assert exc.value.status_code == 503
    assert "Hoelscher proxy" in exc.value.detail
