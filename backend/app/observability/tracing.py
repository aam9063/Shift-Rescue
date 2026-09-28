"""OpenTelemetry → Langfuse Cloud (user decision: no self-hosted Langfuse,
see docs/assumptions.md A4). When tracing is enabled, the Strands native spans
and our own spans export straight to Langfuse Cloud via OTLP/HTTP with Basic
auth; an explicit OTEL endpoint overrides the derived Langfuse one.

The provider is installed once per process (`configure_tracing` is
idempotent); the OTLP exporter import is lazy so a missing extra cannot
break boot.
"""

from typing import Any
from urllib.parse import urlparse

import opentelemetry.trace as trace
import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)

# Global guard: the TracerProvider installed by configure_tracing (None until
# then and after shutdown_tracing).
_tracer_provider: Any | None = None


def configure_tracing(
    settings: Settings,
    *,
    exporter: Any | None = None,
    provider: Any | None = None,
) -> bool:
    """Install the global TracerProvider once; returns True when installed.

    Injectable `exporter`/`provider` replace the OTLPSpanExporter and
    TracerProvider constructions so tests stay hermetic (no network).
    """
    global _tracer_provider
    if _tracer_provider is not None:
        return True
    if not settings.tracing_enabled:
        logger.warning("tracing_disabled", reason="no OTLP endpoint and no Langfuse keys")
        return False

    if provider is None:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": settings.service_name,
                "deployment.environment": settings.app_env,
            }
        )
        provider = TracerProvider(resource=resource)
        if exporter is None:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            auth = settings.traces_auth_header
            headers = {"Authorization": auth} if auth else {}
            exporter = OTLPSpanExporter(endpoint=settings.traces_endpoint, headers=headers)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _tracer_provider = provider
    # Endpoint HOST only: never the auth header, never the keys.
    endpoint = settings.traces_endpoint or ""
    logger.info("tracing_enabled", endpoint_host=urlparse(endpoint).netloc)
    return True


def shutdown_tracing() -> None:
    """Flush and shut down the installed provider; no-op when never configured."""
    global _tracer_provider
    provider = _tracer_provider
    if provider is None:
        return
    _tracer_provider = None
    try:
        provider.force_flush()
        provider.shutdown()
    except Exception as error:  # tracing must never take the API down
        logger.warning("tracing_shutdown_failed", error=str(error)[:200])


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
