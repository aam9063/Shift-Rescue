"""Application settings loaded from environment variables (spec §12)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    service_name: str = "shift-rescue-backend"
    database_url: str = "postgresql+asyncpg://shift_rescue:shift_rescue@localhost:5432/shift_rescue"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-only-secret"
    demo_real_phones: str | None = None  # "Name:+346...|Name:+346..." (max 3, sandbox)


@lru_cache
def get_settings() -> Settings:
    return Settings()
