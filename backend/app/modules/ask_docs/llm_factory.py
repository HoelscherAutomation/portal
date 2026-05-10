"""Resolve current ask-docs config + return the appropriate ChatClient."""
import logging

from fastapi import HTTPException

from app import config as app_config
from app.modules._config_service import load_config
from app.modules.ask_docs.chat_client import ChatClient
from app.modules.ask_docs.llm import AnthropicChatClient
from app.modules.ask_docs.ollama_chat import OllamaChatClient

logger = logging.getLogger(__name__)


async def make_llm_client(config: dict | None = None) -> tuple[ChatClient, str]:
    """Load saved ask-docs config and dispatch to the right backend.

    Returns (client, mode_used) so the orchestrator can persist mode_used to the query log.

    `config` may be passed in by callers that already loaded it (e.g. the
    orchestrator factory also reads `reranker.enabled`). If omitted, we load
    here. This avoids a double DB roundtrip per chat request.
    """
    if config is None:
        config = await load_config("ask-docs")
    mode = config.get("llm_mode", "anthropic")

    if mode == "anthropic":
        anth = config.get("anthropic", {})
        db_key = anth.get("api_key")
        env_key = app_config.get_settings().anthropic_api_key
        key = db_key or env_key
        if not key:
            logger.warning("ask-docs anthropic mode requested but no API key in DB or env")
            raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")
        if not db_key and env_key:
            # Surface the env-fallback once per request so an admin who "cleared" the
            # DB key in the UI can see in logs that env-var is now driving chat.
            logger.info("ask-docs anthropic mode using ANTHROPIC_API_KEY env-var fallback (no DB key set)")
        return (
            AnthropicChatClient(
                api_key=key,
                model=anth.get("model") or app_config.get_settings().anthropic_model,
            ),
            "anthropic",
        )

    if mode == "ollama":
        oll = config.get("ollama", {})
        url = oll.get("url") or ""
        model = oll.get("model") or ""
        if not url or not model:
            logger.warning(
                "ask-docs ollama mode requested but config is incomplete (url=%r, model=%r)",
                url, model,
            )
            raise HTTPException(
                status_code=503,
                detail="Ollama mode selected but URL or model is not set",
            )
        return OllamaChatClient(url=url, model=model), "ollama"

    if mode == "hoelscher_proxy":
        raise HTTPException(
            status_code=503,
            detail="Hoelscher proxy mode is not yet available",
        )

    raise HTTPException(status_code=500, detail=f"Unknown llm_mode: {mode}")
