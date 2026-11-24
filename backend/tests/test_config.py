import pytest

from app.config import Settings

# A 32+ char SECRET_KEY that's NOT in the placeholder allowlist (otherwise
# the validator catches it). Used by these tests only.
_TEST_SECRET = "test-secret-value-of-sufficient-length-1234567890"


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("SECRET_KEY", _TEST_SECRET)
    monkeypatch.setenv("COOKIE_SECURE", "false")

    settings = Settings()
    assert settings.database_url == "postgresql+asyncpg://test:test@localhost/test"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.secret_key == _TEST_SECRET
    assert settings.cookie_secure is False


def test_settings_rejects_short_secret_key(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("SECRET_KEY", "tooshort")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    with pytest.raises(ValueError, match="SECRET_KEY too short"):
        Settings()


def test_settings_rejects_placeholder_secret_key(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("SECRET_KEY", "change-me-to-a-long-random-string")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    with pytest.raises(ValueError, match="placeholder"):
        Settings()


def test_settings_rejects_cors_wildcard_with_credentials(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("SECRET_KEY", _TEST_SECRET)
    monkeypatch.setenv("CORS_ORIGINS", '["*"]')
    with pytest.raises(ValueError, match="unsafe"):
        Settings()


def test_portal_version_comes_from_the_version_file():
    """backend/VERSION is the one version source; the settings default must read it."""
    from pathlib import Path

    from app.config import Settings

    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    assert Settings.model_fields["portal_version"].default == version_file.read_text().strip()
