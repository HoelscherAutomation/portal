from app.config import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("COOKIE_SECURE", "false")

    settings = Settings()
    assert settings.database_url == "postgresql+asyncpg://test:test@localhost/test"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.secret_key == "test-secret"
    assert settings.cookie_secure is False
