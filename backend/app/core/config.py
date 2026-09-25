"""Application settings loaded from environment variables (spec §12).

`Settings` is the single reader of environment configuration: every variable
the runtime consumes is declared here with a type and a default; stale or
unknown variables are ignored (`extra="ignore"`).
"""

import base64
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    service_name: str = "shift-rescue-backend"
    database_url: str = "postgresql+asyncpg://shift_rescue:shift_rescue@localhost:5432/shift_rescue"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-only-secret"
    jwt_expires_minutes: int = 720  # 12 h access tokens (spec §7.5)
    # Comma-separated origins allowed by CORS for the dashboard SPA (spec §7.5).
    cors_origins: str = "http://localhost:5173"
    demo_real_phones: str | None = None  # "Name:+346...|Name:+346..." (max 3, sandbox)

    # Timer backend (spec §7.3): "celery" publishes each timer as one deferred
    # broker task (survives worker restarts, any prefork child can run it);
    # "memory" keeps the in-process SimScheduler for a single-process local run
    # and the eval harness.
    scheduler_backend: str = "celery"

    # Twilio WhatsApp (docs/twilio-sandbox-setup.md)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"  # sandbox default
    twilio_validate_signature: bool = True

    # Privacy (spec §10): message bodies older than this are purged.
    message_retention_days: int = 30

    # LLM provider (ADR-004): OpenAI by default, anthropic/bedrock behind the
    # same factory, `none` disables the LLM path (deterministic parser only).
    llm_provider: str = "openai"
    llm_model_interpreter: str = ""  # empty -> provider default
    llm_temperature: float = 0.0
    llm_max_tokens: int = 500
    llm_timeout_seconds: float = 10.0
    llm_confidence_threshold: float = 0.75
    llm_price_input_per_1k: float = 0.0  # 0.0 -> provider default
    llm_price_output_per_1k: float = 0.0  # 0.0 -> provider default
    openai_api_key: str = ""
    openai_base_url: str | None = None  # OpenAI-compatible gateways (e.g. NaN)
    anthropic_api_key: str = ""
    aws_region: str = "eu-west-1"

    # Observability: OTLP/HTTP traces to Langfuse Cloud (ADR-003).
    otel_exporter_otlp_endpoint: str | None = None  # explicit override
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    sentry_dsn: str = ""  # declared for .env parity; Sentry init not wired yet

    @property
    def cors_origin_list(self) -> list[str]:
        """Parsed CORS origins: exactly the configured ones, no wildcard."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def llm_enabled(self) -> bool:
        """True unless the provider is explicitly turned off."""
        return self.llm_provider.strip().lower() not in {"", "none", "disabled"}

    @property
    def traces_endpoint(self) -> str | None:
        """OTLP/HTTP endpoint: explicit override, else the Langfuse Cloud one."""
        if self.otel_exporter_otlp_endpoint:
            return self.otel_exporter_otlp_endpoint
        if self.langfuse_public_key and self.langfuse_secret_key:
            return f"{self.langfuse_host.rstrip('/')}/api/public/otel/v1/traces"
        return None

    @property
    def tracing_enabled(self) -> bool:
        return self.traces_endpoint is not None

    @property
    def traces_auth_header(self) -> str | None:
        """Langfuse Basic auth header; None when either key is missing."""
        if not (self.langfuse_public_key and self.langfuse_secret_key):
            return None
        raw = f"{self.langfuse_public_key}:{self.langfuse_secret_key}".encode()
        return f"Basic {base64.b64encode(raw).decode()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
