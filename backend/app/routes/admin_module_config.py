"""Admin per-module config CRUD + probe."""
import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

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
        return ProbeResult(ok=False, error=str(exc)[:500])


async def _resolve_set_markers_for_probe(module_key: str, mode: str, settings: dict) -> dict:
    """If settings contain {"_set": true} markers for secret fields, fill from saved config."""
    saved = await load_config(module_key)
    saved_mode = saved.get(mode, {})
    out = {**settings}
    for path in SECRET_PATHS.get(module_key, []):
        if path[0] != mode:
            continue
        # path is like ("anthropic", "api_key") — for probe we only walk one level into the mode block
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
