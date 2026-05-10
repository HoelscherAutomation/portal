import pytest

from app.modules._config_service import (
    DEFAULTS,
    UnknownModuleError,
    load_config,
    redact_for_response,
    save_config,
)


async def test_load_returns_defaults_when_no_row():
    config = await load_config("ask-docs")
    assert config["llm_mode"] == "anthropic"
    assert config["anthropic"]["model"] == "claude-sonnet-4-6"
    assert config["anthropic"]["api_key"] is None
    assert config["ollama"]["url"] == ""
    assert config["reranker"] == {"enabled": False}


async def test_save_then_load_round_trip_with_secret():
    payload = {
        "llm_mode": "anthropic",
        "anthropic": {"api_key": "sk-test-123", "model": "claude-sonnet-4-6", "max_tokens": 1024},
        "ollama": {"url": "", "model": "", "max_tokens": 1024},
        "hoelscher_proxy": {},
    }
    await save_config("ask-docs", payload, updated_by=None)
    loaded = await load_config("ask-docs")
    assert loaded["anthropic"]["api_key"] == "sk-test-123"
    assert loaded["anthropic"]["model"] == "claude-sonnet-4-6"


async def test_save_updates_existing_row():
    base = {
        "llm_mode": "anthropic",
        "anthropic": {"api_key": "sk-1", "model": "claude-sonnet-4-6", "max_tokens": 1024},
        "ollama": {"url": "", "model": "", "max_tokens": 1024},
        "hoelscher_proxy": {},
    }
    await save_config("ask-docs", base, updated_by=None)
    base["anthropic"]["api_key"] = "sk-2"
    await save_config("ask-docs", base, updated_by=None)
    loaded = await load_config("ask-docs")
    assert loaded["anthropic"]["api_key"] == "sk-2"


async def test_save_validates_against_pydantic_schema():
    bad = {"llm_mode": "INVALID", "anthropic": {}, "ollama": {}, "hoelscher_proxy": {}}
    with pytest.raises(ValueError):
        await save_config("ask-docs", bad, updated_by=None)


async def test_save_unknown_module_raises():
    with pytest.raises(UnknownModuleError):
        await save_config("not-a-real-module", {}, updated_by=None)


async def test_redact_replaces_encrypted_with_set_marker():
    cfg = {
        "llm_mode": "anthropic",
        "anthropic": {"api_key": "sk-real-secret", "model": "claude-sonnet-4-6"},
        "ollama": {"url": "http://x", "model": "llama3"},
    }
    redacted = redact_for_response(cfg, "ask-docs")
    assert redacted["anthropic"]["api_key"] == {"_set": True}
    assert redacted["anthropic"]["model"] == "claude-sonnet-4-6"
    assert redacted["ollama"]["url"] == "http://x"


async def test_redact_marks_unset_secret_as_not_set():
    cfg = {
        "llm_mode": "anthropic",
        "anthropic": {"api_key": None, "model": "claude-sonnet-4-6"},
        "ollama": {"url": "", "model": ""},
    }
    redacted = redact_for_response(cfg, "ask-docs")
    assert redacted["anthropic"]["api_key"] == {"_set": False}


async def test_save_returns_plaintext_not_encrypted_marker():
    """save_config docstring claims the return is plaintext. Without a deepcopy
    of `validated` before encryption, `_set_path` mutated the same nested dict
    that's returned — leaking the encrypted marker back to callers."""
    payload = {
        "llm_mode": "anthropic",
        "anthropic": {"api_key": "sk-test-deepcopy", "model": "claude-sonnet-4-6", "max_tokens": 1024},
        "ollama": {"url": "", "model": "", "max_tokens": 1024},
        "hoelscher_proxy": {},
    }
    result = await save_config("ask-docs", payload, updated_by=None)
    assert result["anthropic"]["api_key"] == "sk-test-deepcopy"  # NOT {"_encrypted": True, ...}


async def test_load_merges_defaults_for_missing_fields():
    """Rows persisted before a new schema field was added must still surface
    that field (with default value) on read — otherwise the frontend crashes
    on `config.<new_field>.<x>` and dispatchers must defensive-`.get()` everywhere."""
    import app.database as db_module
    from app.models import ModuleConfig
    # Insert a row directly via raw SQL/ORM that lacks the `reranker` field
    # (mimicking a row saved before P1.3b was deployed)
    async with db_module.async_session_maker() as session:
        cfg = ModuleConfig(module_key="ask-docs", config={
            "llm_mode": "anthropic",
            "anthropic": {"api_key": None, "model": "claude-sonnet-4-6", "max_tokens": 1024},
            "ollama": {"url": "", "model": "", "max_tokens": 1024},
            "hoelscher_proxy": {},
            # NOTE: no "reranker" key — exactly the pre-P1.3b shape
        })
        session.add(cfg)
        await session.commit()

    config = await load_config("ask-docs")
    # Missing field backfilled from schema defaults
    assert config["reranker"] == {"enabled": False}
    # Existing fields preserved verbatim
    assert config["anthropic"]["model"] == "claude-sonnet-4-6"
    assert config["llm_mode"] == "anthropic"


async def test_save_refreshes_updated_at_on_upsert():
    """SQLAlchemy onupdate hook does NOT fire for dialect-level INSERT ON CONFLICT;
    save_config must explicitly set updated_at in the conflict clause."""
    import asyncio
    from sqlalchemy import select
    import app.database as db_module
    from app.models import ModuleConfig

    base = {
        "llm_mode": "anthropic",
        "anthropic": {"api_key": "sk-1", "model": "claude-sonnet-4-6", "max_tokens": 1024},
        "ollama": {"url": "", "model": "", "max_tokens": 1024},
        "hoelscher_proxy": {},
    }
    await save_config("ask-docs", base, updated_by=None)

    async with db_module.async_session_maker() as session:
        first = (await session.execute(
            select(ModuleConfig).where(ModuleConfig.module_key == "ask-docs")
        )).scalar_one()
        first_ts = first.updated_at

    await asyncio.sleep(0.05)
    base["anthropic"]["max_tokens"] = 2048
    await save_config("ask-docs", base, updated_by=None)

    async with db_module.async_session_maker() as session:
        second = (await session.execute(
            select(ModuleConfig).where(ModuleConfig.module_key == "ask-docs")
        )).scalar_one()
        assert second.updated_at > first_ts, (
            f"updated_at should refresh on upsert (was {first_ts}, now {second.updated_at})"
        )


async def test_save_preserves_existing_secret_when_payload_uses_set_marker():
    """If the UI sends `{"_set": true}` it means 'keep existing value' — don't clobber."""
    initial = {
        "llm_mode": "anthropic",
        "anthropic": {"api_key": "sk-original", "model": "claude-sonnet-4-6", "max_tokens": 1024},
        "ollama": {"url": "", "model": "", "max_tokens": 1024},
        "hoelscher_proxy": {},
    }
    await save_config("ask-docs", initial, updated_by=None)

    update = dict(initial)
    update["anthropic"] = {**initial["anthropic"], "api_key": {"_set": True}, "model": "claude-opus-4-7"}
    await save_config("ask-docs", update, updated_by=None)

    loaded = await load_config("ask-docs")
    assert loaded["anthropic"]["api_key"] == "sk-original"
    assert loaded["anthropic"]["model"] == "claude-opus-4-7"
