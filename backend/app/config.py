from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Common weak / placeholder SECRET_KEY values we should refuse at startup.
_WEAK_SECRET_KEYS = {
    "change-me-to-a-long-random-string",
    "change-me",
    "secret",
    "changeme",
    "default",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    database_url: str
    redis_url: str
    secret_key: str
    cookie_secure: bool = False
    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("secret_key")
    @classmethod
    def _validate_secret_key(cls, v: str) -> str:
        """SECRET_KEY signs JWTs AND derives the Fernet key for module_configs
        secret encryption. A weak/default value compromises both auth and
        secrets-at-rest. Refuse < 32 chars or any well-known placeholder."""
        if len(v) < 32:
            raise ValueError(
                f"SECRET_KEY too short ({len(v)} chars); need ≥ 32. "
                "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        if v.strip().lower() in _WEAK_SECRET_KEYS:
            raise ValueError(
                "SECRET_KEY appears to be a placeholder/default. "
                "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        return v

    @model_validator(mode="after")
    def _validate_cors_credentials_combo(self) -> "Settings":
        """`Allow-Origin: *` with credentials is a known browser-bypassable
        combination (FastAPI/Starlette doesn't enforce the incompatibility).
        Refuse the misconfig at startup."""
        if "*" in self.cors_origins:
            raise ValueError(
                "CORS_ORIGINS=['*'] is unsafe (the portal sends cookies). "
                "Set CORS_ORIGINS to your portal origin(s) explicitly."
            )
        return self

    test_database_url: str | None = None
    uploads_path: str = "/app/data/uploads"
    sql_echo: bool = False
    reset_password_secret: str | None = None
    verification_secret: str | None = None
    # Phone-home (P0d.2b) — opt-in. If oc_url is unset, the loop never starts.
    oc_url: str | None = None
    oc_token: str | None = None
    phone_home_interval_seconds: int = 300
    portal_version: str = "0.5.0"
    # Ask Docs (P1.1)
    qdrant_url: str = "http://qdrant:6333"
    ollama_url: str = "http://ollama:11434"
    ask_docs_embedding_model: str = "nomic-embed-text"
    ask_docs_chunk_size_tokens: int = 1024
    ask_docs_chunk_overlap_tokens: int = 128
    # Ask Docs (P1.2 — chat)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"
    ask_docs_top_k: int = 8
    ask_docs_max_answer_tokens: int = 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


def resolve_test_database_url() -> str:
    """Test DB URL — explicit override, else derive from production URL with _test suffix."""
    settings = get_settings()
    if settings.test_database_url:
        return settings.test_database_url
    base, _, dbname = settings.database_url.rpartition("/")
    return f"{base}/{dbname}_test"
