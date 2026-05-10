"""Per-module Pydantic schemas for config validation."""
from typing import Literal

from pydantic import BaseModel, Field


class AnthropicConfig(BaseModel):
    api_key: str | None = None
    model: str = "claude-sonnet-4-6"
    max_tokens: int = Field(default=1024, ge=1, le=8192)


class OllamaConfig(BaseModel):
    url: str = ""
    model: str = ""
    max_tokens: int = Field(default=1024, ge=1, le=8192)


class RerankerConfig(BaseModel):
    enabled: bool = False


class AskDocsConfigSchema(BaseModel):
    llm_mode: Literal["anthropic", "ollama", "hoelscher_proxy"] = "anthropic"
    anthropic: AnthropicConfig = AnthropicConfig()
    ollama: OllamaConfig = OllamaConfig()
    hoelscher_proxy: dict = Field(default_factory=dict)
    reranker: RerankerConfig = RerankerConfig()


# Per-module schema registry. To add a new module's config: register here.
SCHEMAS: dict[str, type[BaseModel]] = {
    "ask-docs": AskDocsConfigSchema,
}

# Per-module secret JSON paths. Walked by save_config to encrypt + redact_for_response to mask.
SECRET_PATHS: dict[str, list[tuple[str, ...]]] = {
    "ask-docs": [
        ("anthropic", "api_key"),
    ],
}
