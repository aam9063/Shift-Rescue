"""OpenTelemetry → Langfuse Cloud (user decision: no self-hosted Langfuse,
see docs/assumptions.md A4). When OTEL_EXPORTER_OTLP_ENDPOINT is set, the
Strands native spans and our own spans export straight to Langfuse Cloud via
OTLP; LANGFUSE_PUBLIC_KEY/SECRET_KEY authenticate the endpoint.
"""

import os
from typing import Any


def is_otel_enabled() -> bool:
    return bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))


def rescue_span_attributes(
    *,
    rescue_id: str | None = None,
    prompt_version: str | None = None,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: float | None = None,
    latency_ms: float | None = None,
) -> dict[str, Any]:
    """Span attributes for one LLM call, grouped per rescue in Langfuse."""
    attrs: dict[str, Any] = {}
    if rescue_id is not None:
        attrs["rescue_id"] = rescue_id
    if prompt_version is not None:
        attrs["prompt_version"] = prompt_version
    if model is not None:
        attrs["model"] = model
    if input_tokens is not None:
        attrs["input_tokens"] = input_tokens
    if output_tokens is not None:
        attrs["output_tokens"] = output_tokens
    if cost_usd is not None:
        attrs["cost_usd"] = cost_usd
    if latency_ms is not None:
        attrs["latency_ms"] = latency_ms
    return attrs
