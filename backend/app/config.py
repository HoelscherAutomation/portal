from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    database_url: str
    redis_url: str
    secret_key: str
    cookie_secure: bool = False
    cors_origins: list[str] = ["http://localhost:5173"]
    test_database_url: str | None = None
    uploads_path: str = "/app/data/uploads"
    reset_password_secret: str | None = None
    verification_secret: str | None = None
    sql_echo: bool = False


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
