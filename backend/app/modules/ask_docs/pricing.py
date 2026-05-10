"""Hardcoded LLM pricing for the admin dashboard cost estimate.

Update PRICES_PER_M_TOKENS + LAST_UPDATED whenever Anthropic publishes new prices.
The dashboard tooltip surfaces LAST_UPDATED so the customer admin knows the
estimate may be stale.

Approximation: we average input + output token prices weighted ~3:1 (typical
chat shape) and apply that to the total tokens_used. Good enough for a
"how much have I spent this month" badge; not a billing source.
"""

LAST_UPDATED = "2026-05-10"

# USD per million tokens, by (mode, model). The "*" model is a fallback
# applied when a specific model isn't listed.
PRICES_PER_M_TOKENS: dict[tuple[str, str], float] = {
    ("anthropic", "claude-sonnet-4-6"): 6.0,
    ("anthropic", "claude-opus-4-7"): 30.0,
    ("anthropic", "*"): 6.0,
    ("ollama", "*"): 0.0,
    ("hoelscher_proxy", "*"): 7.5,
}


def estimate_cost_usd(mode: str, model: str | None, tokens: int) -> float:
    """Return USD cost estimate for `tokens` consumed under (mode, model).

    Lookup order: (mode, model) → (mode, "*") → 0.0 (unknown mode).
    Never returns negative.
    """
    if tokens <= 0:
        return 0.0
    price = PRICES_PER_M_TOKENS.get((mode, model or ""))
    if price is None:
        price = PRICES_PER_M_TOKENS.get((mode, "*"), 0.0)
    return round((tokens / 1_000_000) * price, 4)
