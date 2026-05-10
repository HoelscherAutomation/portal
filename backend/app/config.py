from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    database_url: str
    redis_url: str
    secret_key: str
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
