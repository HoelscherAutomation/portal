"""Admin per-module config CRUD + probe."""
import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.backend import current_superuser
from app.secret_scrub import scrub_secrets as _scrub_secrets
from app.models import User
from app.modules._config_schemas import SCHEMAS, SECRET_PATHS
from app.modules._config_service import (
    UnknownModuleError,
    load_config,
    redact_for_response,
    save_config,
)
from app.modules.ask_docs.dashboard_service import compute_dashboard
from app.modules.ask_docs.llm import AnthropicChatClient
from app.modules.ask_docs.ollama_chat import OllamaChatClient
from app.modules.ask_docs.queries_service import (
    QueryNotFound, get_query_detail, list_queries,
)

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

    # Build the client outside the timed coroutine so we can guarantee aclose
    # in finally — even if asyncio.wait_for cancels the inner task mid-stream.
    # Without this, every probe (especially timed-out ones) leaks an httpx pool.
    try:
        client = _build_transient_client(body.mode, settings)
    except HTTPException:
        raise
    except ValueError as exc:
        return ProbeResult(ok=False, error=_scrub_secrets(str(exc))[:500])

    async def _do_probe():
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

    try:
        await asyncio.wait_for(_do_probe(), timeout=10.0)
        latency_ms = int((time.monotonic() - started) * 1000)
        return ProbeResult(ok=True, latency_ms=latency_ms)
    except asyncio.TimeoutError:
        return ProbeResult(ok=False, error="Probe timed out after 10s")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Probe failed for mode=%s", body.mode)
        return ProbeResult(ok=False, error=_scrub_secrets(str(exc))[:500])
    finally:
        if hasattr(client, "aclose"):
            try:
                await client.aclose()
            except Exception:
                logger.exception("Failed to close transient probe client")


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
    """Construct a one-shot client from raw settings — does not touch saved config.

    SECURITY: Ollama mode takes an admin-supplied URL and makes an outbound HTTP request
    from the backend. This is an intentional SSRF surface — bounded to the superuser
    trust tier per the threat model (single-tenant homelab, admin already has DB access).
    If we ever add untrusted-tenant config writes, restrict to http(s):// + non-RFC1918.
    """
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


@router.get("/ask-docs/dashboard")
async def get_dashboard(
    _user: User = Depends(current_superuser),
):
    """Aggregated metrics for the Ask Docs admin dashboard. Polled every 30s by the UI."""
    return await compute_dashboard()


@router.get("/ask-docs/queries")
async def get_queries(
    limit: int = 100,
    offset: int = 0,
    _user: User = Depends(current_superuser),
):
    """Paginated query log, newest first."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="limit must be 1-200")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must be >= 0")
    return await list_queries(limit=limit, offset=offset)


@router.get("/ask-docs/queries/{query_id}")
async def get_query(
    query_id: int,
    _user: User = Depends(current_superuser),
):
    """Drill-down: full query + answer + sources_used."""
    try:
        return await get_query_detail(query_id)
    except QueryNotFound:
        raise HTTPException(status_code=404, detail="Query not found")
