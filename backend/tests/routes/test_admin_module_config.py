import pytest
from httpx import AsyncClient

from tests.test_auth import _create_user


async def _login(client: AsyncClient, *, superuser: bool = True):
    email = "admin@example.com" if superuser else "user@example.com"
    await _create_user(email, "test-password-123", superuser=superuser)
    r = await client.post("/api/auth/login", data={"username": email, "password": "test-password-123"})
    assert r.status_code in (200, 204)


async def test_get_config_requires_superuser(client: AsyncClient):
    response = await client.get("/api/admin/modules/ask-docs/config")
    assert response.status_code == 401

    await _login(client, superuser=False)
    response = await client.get("/api/admin/modules/ask-docs/config")
    assert response.status_code == 403


async def test_get_config_returns_defaults_when_unset(client: AsyncClient):
    await _login(client)
    response = await client.get("/api/admin/modules/ask-docs/config")
    assert response.status_code == 200
    body = response.json()
    assert body["llm_mode"] == "anthropic"
    assert body["anthropic"]["api_key"] == {"_set": False}
    assert body["anthropic"]["model"] == "claude-sonnet-4-6"


async def test_get_config_returns_redacted_after_save(client: AsyncClient):
    await _login(client)
    payload = {
        "llm_mode": "anthropic",
        "anthropic": {"api_key": "sk-real", "model": "claude-sonnet-4-6", "max_tokens": 1024},
        "ollama": {"url": "", "model": "", "max_tokens": 1024},
        "hoelscher_proxy": {},
    }
    save = await client.put("/api/admin/modules/ask-docs/config", json=payload)
    assert save.status_code == 200

    get = await client.get("/api/admin/modules/ask-docs/config")
    body = get.json()
    assert body["anthropic"]["api_key"] == {"_set": True}
    assert body["anthropic"]["model"] == "claude-sonnet-4-6"


async def test_put_config_validates_schema(client: AsyncClient):
    await _login(client)
    bad = {"llm_mode": "INVALID", "anthropic": {}, "ollama": {}, "hoelscher_proxy": {}}
    response = await client.put("/api/admin/modules/ask-docs/config", json=bad)
    assert response.status_code == 422


async def test_put_with_set_marker_preserves_existing_secret(client: AsyncClient):
    await _login(client)
    initial = {
        "llm_mode": "anthropic",
        "anthropic": {"api_key": "sk-saved", "model": "claude-sonnet-4-6", "max_tokens": 1024},
        "ollama": {"url": "", "model": "", "max_tokens": 1024},
        "hoelscher_proxy": {},
    }
    await client.put("/api/admin/modules/ask-docs/config", json=initial)

    update = {**initial, "anthropic": {**initial["anthropic"], "api_key": {"_set": True}, "max_tokens": 2048}}
    r = await client.put("/api/admin/modules/ask-docs/config", json=update)
    assert r.status_code == 200

    from app.modules._config_service import load_config
    cfg = await load_config("ask-docs")
    assert cfg["anthropic"]["api_key"] == "sk-saved"
    assert cfg["anthropic"]["max_tokens"] == 2048


async def test_probe_with_valid_anthropic_settings(client: AsyncClient, monkeypatch):
    """Probe builds a transient client from the supplied settings, not from saved config."""

    class FakeAnth:
        def __init__(self, *, api_key, model, client=None):
            self._model = model
        async def stream_chat(self, *, system, user, max_tokens, on_final_usage=None):
            yield "ok"
            if on_final_usage:
                on_final_usage({"input_tokens": 1, "output_tokens": 1})

    monkeypatch.setattr("app.routes.admin_module_config.AnthropicChatClient", FakeAnth)
    await _login(client)
    body = {
        "mode": "anthropic",
        "settings": {"api_key": "sk-test", "model": "claude-sonnet-4-6", "max_tokens": 1024},
    }
    r = await client.post("/api/admin/modules/ask-docs/config/probe", json=body)
    assert r.status_code == 200
    result = r.json()
    assert result["ok"] is True
    assert "latency_ms" in result


async def test_probe_with_failing_client_returns_error(client: AsyncClient, monkeypatch):
    class FailingAnth:
        def __init__(self, **kwargs): pass
        async def stream_chat(self, *, system, user, max_tokens, on_final_usage=None):
            raise RuntimeError("simulated 401: invalid api key")
            yield  # unreachable

    monkeypatch.setattr("app.routes.admin_module_config.AnthropicChatClient", FailingAnth)
    await _login(client)
    body = {
        "mode": "anthropic",
        "settings": {"api_key": "sk-bad", "model": "claude-sonnet-4-6", "max_tokens": 1024},
    }
    r = await client.post("/api/admin/modules/ask-docs/config/probe", json=body)
    assert r.status_code == 200
    result = r.json()
    assert result["ok"] is False
    assert "invalid api key" in result["error"]


async def test_probe_with_set_marker_uses_saved_secret(client: AsyncClient, monkeypatch):
    """If probe payload's api_key is `{"_set": true}`, server should fill from saved config."""

    captured = {}
    class FakeAnth:
        def __init__(self, *, api_key, model, client=None):
            captured["api_key"] = api_key
        async def stream_chat(self, *, system, user, max_tokens, on_final_usage=None):
            yield "ok"

    monkeypatch.setattr("app.routes.admin_module_config.AnthropicChatClient", FakeAnth)
    await _login(client)

    # Save a real key first
    await client.put("/api/admin/modules/ask-docs/config", json={
        "llm_mode": "anthropic",
        "anthropic": {"api_key": "sk-saved", "model": "claude-sonnet-4-6", "max_tokens": 1024},
        "ollama": {"url": "", "model": "", "max_tokens": 1024},
        "hoelscher_proxy": {},
    })

    body = {
        "mode": "anthropic",
        "settings": {"api_key": {"_set": True}, "model": "claude-sonnet-4-6", "max_tokens": 1024},
    }
    r = await client.post("/api/admin/modules/ask-docs/config/probe", json=body)
    assert r.status_code == 200
    assert captured["api_key"] == "sk-saved"
