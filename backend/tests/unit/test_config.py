"""Unit tests for application settings."""

from app.core.config import Settings


def test_settings_defaults_to_local_environment() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "local"


def test_settings_exposes_database_and_redis_urls() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url.startswith("redis://")


def test_settings_reads_environment_overrides() -> None:
    settings = Settings(_env_file=None, app_env="demo", database_url="postgresql+asyncpg://x/y")

    assert settings.app_env == "demo"
    assert settings.database_url == "postgresql+asyncpg://x/y"
