"""Resolve current ask-docs config + return the appropriate ChatClient."""
import logging

from fastapi import HTTPException

from app import config as app_config
from app.modules._config_service import load_config
from app.modules.ask_docs.chat_client import ChatClient
from app.modules.ask_docs.llm import AnthropicChatClient
from app.modules.ask_docs.ollama_chat import OllamaChatClient

logger = logging.getLogger(__name__)


async def make_llm_client() -> tuple[ChatClient, str]:
    """Load saved ask-docs config and dispatch to the right backend.

    Returns (client, mode_used) so the orchestrator can persist mode_used to the query log.
    """
    config = await load_config("ask-docs")
    mode = config.get("llm_mode", "anthropic")

    if mode == "anthropic":
        anth = config.get("anthropic", {})
        key = anth.get("api_key") or app_config.get_settings().anthropic_api_key
        if not key:
            raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")
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
