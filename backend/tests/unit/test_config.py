"""Unit tests for application settings."""

import base64

import pytest

from app.core.config import Settings

TRACE_ENV_VARS = ("OTEL_EXPORTER_OTLP_ENDPOINT", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")


@pytest.fixture(autouse=True)
def clean_trace_env(monkeypatch):
    """Keep host environment trace variables out of these unit tests."""
    for name in TRACE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {"_env_file": None}
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


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


# --- llm_enabled -------------------------------------------------------------


def test_llm_disabled_for_none_disabled_and_empty() -> None:
    for provider in ("none", "disabled", "", "  "):
        assert make_settings(llm_provider=provider).llm_enabled is False


def test_llm_enabled_for_known_and_unknown_providers() -> None:
    assert make_settings(llm_provider="openai").llm_enabled is True
    assert make_settings(llm_provider="Bedrock ").llm_enabled is True


# --- traces_endpoint ---------------------------------------------------------


def test_traces_endpoint_explicit_override_wins() -> None:
    settings = make_settings(
        otel_exporter_otlp_endpoint="https://collector.example.com/v1/traces",
        langfuse_public_key="pk",
        langfuse_secret_key="sk",
    )
    assert settings.traces_endpoint == "https://collector.example.com/v1/traces"


def test_traces_endpoint_derived_from_langfuse_host() -> None:
    settings = make_settings(langfuse_public_key="pk", langfuse_secret_key="sk")
    assert settings.traces_endpoint == "https://cloud.langfuse.com/api/public/otel/v1/traces"


def test_traces_endpoint_strips_trailing_slash_from_langfuse_host() -> None:
    settings = make_settings(
        langfuse_host="https://eu.cloud.langfuse.com/",
        langfuse_public_key="pk",
        langfuse_secret_key="sk",
    )
    assert settings.traces_endpoint == "https://eu.cloud.langfuse.com/api/public/otel/v1/traces"


def test_traces_endpoint_none_without_langfuse_keys() -> None:
    assert make_settings().traces_endpoint is None
    assert make_settings(langfuse_public_key="pk").traces_endpoint is None
    assert make_settings(langfuse_secret_key="sk").traces_endpoint is None


def test_tracing_enabled_follows_traces_endpoint() -> None:
    assert make_settings().tracing_enabled is False
    assert (
        make_settings(langfuse_public_key="pk", langfuse_secret_key="sk").tracing_enabled is True
    )


# --- traces_auth_header ------------------------------------------------------


def test_traces_auth_header_is_basic_base64() -> None:
    settings = make_settings(langfuse_public_key="pk_test", langfuse_secret_key="sk_test")
    raw = base64.b64encode(b"pk_test:sk_test").decode()
    assert settings.traces_auth_header == f"Basic {raw}"


def test_traces_auth_header_none_without_both_keys() -> None:
    assert make_settings().traces_auth_header is None
    assert make_settings(langfuse_public_key="pk").traces_auth_header is None
