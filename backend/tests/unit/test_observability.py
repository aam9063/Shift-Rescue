"""Observability wiring tests (spec §9.1): OTel to Langfuse Cloud, phone
masking, structured log enrichment, TracerProvider installation."""

import opentelemetry.trace as trace
import pytest
from opentelemetry.sdk.trace import TracerProvider
from structlog.testing import capture_logs

import app.observability.tracing as tracing
from app.core.config import Settings
from app.observability.redaction import mask_phone
from app.observability.tracing import (
    configure_tracing,
    rescue_span_attributes,
    shutdown_tracing,
)


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {"_env_file": None}
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def reset_tracing_guard(monkeypatch):
    """Start every test with tracing unconfigured; shut down what tests installed."""
    monkeypatch.setattr(tracing, "_tracer_provider", None)
    yield
    shutdown_tracing()
    monkeypatch.setattr(tracing, "_tracer_provider", None)


class StubExporter:
    def __init__(self) -> None:
        self.shutdown_calls = 0

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class StubProvider:
    def __init__(self) -> None:
        self.span_processors: list[object] = []
        self.shutdown_calls = 0

    def add_span_processor(self, processor: object) -> None:
        self.span_processors.append(processor)

    def force_flush(self) -> bool:
        return True

    def shutdown(self) -> None:
        self.shutdown_calls += 1


def test_mask_phone_hides_all_but_last_digits() -> None:
    masked = mask_phone("+34600000001")
    assert "6000000" not in masked
    assert masked.endswith("01")
    assert masked.startswith("+")


def test_mask_phone_handles_short_or_garbage() -> None:
    assert mask_phone("") == ""
    assert mask_phone("not-a-phone") == "not-a-phone"


def test_tracing_disabled_without_keys() -> None:
    settings = Settings(_env_file=None)
    assert settings.tracing_enabled is False
    assert configure_tracing(settings) is False


def test_tracing_enabled_with_langfuse_cloud_settings() -> None:
    settings = Settings(
        _env_file=None,
        langfuse_public_key="pk-lf-test",
        langfuse_secret_key="sk-lf-test",
    )
    assert settings.tracing_enabled is True
    assert settings.traces_endpoint == "https://cloud.langfuse.com/api/public/otel/v1/traces"


def test_rescue_span_attributes_carry_spec_metadata() -> None:
    attrs = rescue_span_attributes(
        rescue_id="case_1",
        prompt_version="interpreter_v1",
        model="claude-haiku-4-5",
        input_tokens=120,
        output_tokens=45,
        cost_usd=0.0003,
        latency_ms=812.0,
    )
    assert attrs["rescue_id"] == "case_1"
    assert attrs["prompt_version"] == "interpreter_v1"
    assert attrs["model"] == "claude-haiku-4-5"
    assert attrs["input_tokens"] == 120
    assert attrs["cost_usd"] == 0.0003


# --- configure_tracing -------------------------------------------------------


def test_configure_tracing_returns_false_without_keys() -> None:
    with capture_logs() as logs:
        assert configure_tracing(make_settings()) is False
    assert logs[0]["event"] == "tracing_disabled"


def test_configure_tracing_installs_exactly_once(monkeypatch) -> None:
    settings = make_settings(langfuse_public_key="pk", langfuse_secret_key="sk")
    stub_provider = StubProvider()

    installed: list[object] = []
    monkeypatch.setattr(trace, "set_tracer_provider", lambda provider: installed.append(provider))

    with capture_logs() as logs:
        assert configure_tracing(settings, exporter=StubExporter(), provider=stub_provider) is True
        # Second call: idempotent, must not install anything again.
        assert configure_tracing(settings, exporter=StubExporter(), provider=StubProvider()) is True

    assert installed == [stub_provider]
    assert logs[0]["event"] == "tracing_enabled"
    assert logs[0]["endpoint_host"] == "cloud.langfuse.com"
    assert all("pk" not in str(entry) and "Basic" not in str(entry) for entry in logs)


def test_configure_tracing_with_real_provider_builds_exporter_path(monkeypatch) -> None:
    """Exporter injected, provider built internally (no network: stub exporter)."""
    settings = make_settings(
        service_name="shift-rescue-test",
        app_env="test",
        langfuse_public_key="pk",
        langfuse_secret_key="sk",
    )
    installed: list[object] = []
    monkeypatch.setattr(trace, "set_tracer_provider", lambda provider: installed.append(provider))

    with capture_logs():
        assert configure_tracing(settings, exporter=StubExporter()) is True

    assert len(installed) == 1
    assert isinstance(installed[0], TracerProvider)


# --- shutdown_tracing --------------------------------------------------------


def test_shutdown_tracing_flushes_and_shuts_down_installed_provider() -> None:
    stub_provider = StubProvider()
    tracing._tracer_provider = stub_provider

    shutdown_tracing()

    assert stub_provider.shutdown_calls == 1
    assert tracing._tracer_provider is None


def test_shutdown_tracing_is_safe_when_never_configured() -> None:
    shutdown_tracing()  # must not raise
    assert tracing._tracer_provider is None
