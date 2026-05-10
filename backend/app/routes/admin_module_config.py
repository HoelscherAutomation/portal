"""Admin per-module config CRUD + probe."""
import asyncio
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# Match common secret patterns that LLM client errors might embed in their messages.
# Defense-in-depth: SDKs generally don't leak credentials in exceptions, but if a
# transport-layer error includes a URL or auth header containing the key, we strip it
# before surfacing to the customer admin.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{10,}"),       # Anthropic, OpenAI-style API keys
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+"),    # Authorization header
]


def _scrub_secrets(text: str) -> str:
    """Replace any obvious credential patterns with [REDACTED]."""
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text

from app.auth.backend import current_superuser
from app.models import User
from app.modules._config_schemas import SCHEMAS, SECRET_PATHS
from app.modules._config_service import (
    UnknownModuleError,
    load_config,
    redact_for_response,
    save_config,
)
from app.modules.ask_docs.llm import AnthropicChatClient
from app.modules.ask_docs.ollama_chat import OllamaChatClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/modules", tags=["admin-module-config"])


class ProbeRequest(BaseModel):
    mode: str
    settings: dict[str, Any]


class ProbeResult(BaseModel):
    ok: bool
    latency_ms: int | None = None
    error: str | None = None


@router.get("/{module_key}/config")
async def get_config(
    module_key: str,
    _user: User = Depends(current_superuser),
):
    if module_key not in SCHEMAS:
        raise HTTPException(status_code=404, detail=f"No config schema for module: {module_key}")
    config = await load_config(module_key)
    return redact_for_response(config, module_key)


@router.put("/{module_key}/config")
async def put_config(
    module_key: str,
    payload: dict,
    user: User = Depends(current_superuser),
):
    if module_key not in SCHEMAS:
        raise HTTPException(status_code=404, detail=f"No config schema for module: {module_key}")
    try:
        await save_config(module_key, payload, updated_by=user.id)
    except (ValueError, UnknownModuleError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    fresh = await load_config(module_key)
    return redact_for_response(fresh, module_key)


@router.post("/{module_key}/config/probe", response_model=ProbeResult)
async def probe_config(
    module_key: str,
    body: ProbeRequest,
    _user: User = Depends(current_superuser),
):
    if module_key != "ask-docs":
        raise HTTPException(status_code=404, detail="Probe only supported for ask-docs in MVP")

    settings = await _resolve_set_markers_for_probe(module_key, body.mode, body.settings)
    started = time.monotonic()

    try:
        async def _do_probe():
            client = _build_transient_client(body.mode, settings)
            received = ""
            async for delta in client.stream_chat(
                system="You answer with exactly one word.",
                user="Say 'ok'.",
                max_tokens=8,
            ):
                received += delta
                if len(received) > 32:
                    break
            return received

        await asyncio.wait_for(_do_probe(), timeout=10.0)
        latency_ms = int((time.monotonic() - started) * 1000)
        return ProbeResult(ok=True, latency_ms=latency_ms)
    except asyncio.TimeoutError:
        return ProbeResult(ok=False, error="Probe timed out after 10s")
    except Exception as exc:
        logger.exception("Probe failed for mode=%s", body.mode)
        return ProbeResult(ok=False, error=_scrub_secrets(str(exc))[:500])


async def _resolve_set_markers_for_probe(module_key: str, mode: str, settings: dict) -> dict:
    """If settings contain {"_set": true} markers for secret fields, fill from saved config.

    Only handles 2-tuple secret paths shaped (mode, leaf) — the supplied probe `settings`
    dict is just the per-mode block (no outer mode key), so deeper paths can't be walked
    with this function's contract. Skip with a warning if a registered path is deeper;
    a future module author will see the log instead of silent garbage in their probe.
    """
    saved = await load_config(module_key)
    saved_mode = saved.get(mode, {})
    out = {**settings}
    for path in SECRET_PATHS.get(module_key, []):
        if path[0] != mode:
            continue
        if len(path) != 2:
            logger.warning(
                "Probe skipping deep secret path %s for module=%s mode=%s — only 2-tuple paths are supported",
                path, module_key, mode,
            )
            continue
        leaf = path[-1]
        incoming = out.get(leaf)
        if isinstance(incoming, dict) and incoming.get("_set") is True:
            out[leaf] = saved_mode.get(leaf)
    return out


def _build_transient_client(mode: str, settings: dict):
    """Construct a one-shot client from raw settings — does not touch saved config."""
    if mode == "anthropic":
        if not settings.get("api_key"):
            raise ValueError("Anthropic API key is required")
        return AnthropicChatClient(
            api_key=settings["api_key"],
            model=settings.get("model") or "claude-sonnet-4-6",
        )
    if mode == "ollama":
        if not settings.get("url") or not settings.get("model"):
            raise ValueError("Ollama url and model are required")
        return OllamaChatClient(url=settings["url"], model=settings["model"])
    if mode == "hoelscher_proxy":
        raise ValueError("Hoelscher proxy mode is not yet available")
    raise ValueError(f"Unknown mode: {mode}")
