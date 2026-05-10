"""Defensive credential redaction for error messages surfaced to admins.

Used by:
- admin probe endpoint (LLM client errors that might embed an API key)
- ask_docs worker (indexing/embedding errors that include httpx URLs)
- anywhere else exception text is persisted or returned to a UI

WHEN ADDING A NEW PROVIDER: append its key prefix to _SECRET_PATTERNS.
Currently covered:
  - Anthropic / OpenAI:  sk-...
  - Voyage AI:           pa-...
  - Generic Bearer:      Bearer ...
  - HTTP basic auth:     Basic <base64>
"""
import re

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"pa-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+"),
    re.compile(r"Basic\s+[A-Za-z0-9+/=]+"),
]


def scrub_secrets(text: str) -> str:
    """Replace any obvious credential patterns with [REDACTED]."""
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text
