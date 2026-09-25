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

    # Twilio WhatsApp (docs/twilio-sandbox-setup.md)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"  # sandbox default
    twilio_validate_signature: bool = True

    # Privacy (spec §10): message bodies older than this are purged.
    message_retention_days: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
