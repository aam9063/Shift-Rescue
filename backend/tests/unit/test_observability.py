"""Observability wiring tests (spec §9.1): OTel to Langfuse Cloud, phone
masking, structured log enrichment."""

from app.observability.redaction import mask_phone
from app.observability.tracing import (
    is_otel_enabled,
    rescue_span_attributes,
)


def test_mask_phone_hides_all_but_last_digits() -> None:
    masked = mask_phone("+34600000001")
    assert "6000000" not in masked
    assert masked.endswith("01")
    assert masked.startswith("+")


def test_mask_phone_handles_short_or_garbage() -> None:
    assert mask_phone("") == ""
    assert mask_phone("not-a-phone") == "not-a-phone"


def test_otel_disabled_without_env(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert is_otel_enabled() is False


def test_otel_enabled_with_langfuse_cloud_env(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://cloud.langfuse.com/api/public/otel/v1/traces")
    assert is_otel_enabled() is True


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
