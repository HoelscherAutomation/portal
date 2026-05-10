from app.modules.ask_docs.pricing import LAST_UPDATED, estimate_cost_usd


def test_known_mode_and_model():
    # 1M tokens at $6/M = $6.00
    assert estimate_cost_usd("anthropic", "claude-sonnet-4-6", 1_000_000) == 6.0


def test_mode_wildcard_fallback():
    # ollama uses wildcard pricing (free)
    assert estimate_cost_usd("ollama", "llama3.1:8b", 100_000_000) == 0.0


def test_unknown_mode_returns_zero():
    assert estimate_cost_usd("imaginary", "model-x", 1_000_000) == 0.0


def test_zero_tokens_returns_zero():
    assert estimate_cost_usd("anthropic", "claude-sonnet-4-6", 0) == 0.0


def test_partial_million_scales_linearly():
    # 500K at $6/M = $3.00
    assert estimate_cost_usd("anthropic", "claude-sonnet-4-6", 500_000) == 3.0


def test_last_updated_is_iso_date_string():
    # Defensive: future operator should be able to parse this
    from datetime import date
    assert date.fromisoformat(LAST_UPDATED)
