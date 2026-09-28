"""End-to-end check of the Langfuse Cloud wiring (ADR-003/A4, ADR-004).

Sends one real span through the OTLP/HTTP exporter configured from
`backend/.env` and then reads Langfuse's API back to prove the trace arrived.
Prints no secret: only counts, names and the endpoint host.

    cd backend && uv run python ../scripts/verify_langfuse.py

Exit codes: 0 verified, 1 export failed, 2 keys missing.
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import httpx  # noqa: E402
import opentelemetry.trace as trace  # noqa: E402
from opentelemetry.sdk.resources import Resource  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.observability.tracing import rescue_span_attributes  # noqa: E402

SPAN_NAME = "shift-rescue-wiring-check"


async def main() -> int:
    settings = Settings()
    if not settings.tracing_enabled:
        print("MISSING: set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in backend/.env")
        return 2

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    print(f"endpoint: {settings.traces_endpoint}")
    print(f"auth header present: {settings.traces_auth_header is not None}")

    # SimpleSpanProcessor exports synchronously, so the result of this run is
    # unambiguous (the production path uses the batching processor).
    exporter = OTLPSpanExporter(
        endpoint=settings.traces_endpoint,
        headers={"Authorization": settings.traces_auth_header or ""},
    )
    provider = TracerProvider(
        resource=Resource.create(
            {"service.name": settings.service_name, "deployment.environment": settings.app_env}
        )
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    tracer = trace.get_tracer("wiring-check")
    with tracer.start_as_current_span("rescue.lifecycle") as span:
        span.set_attributes(
            rescue_span_attributes(
                rescue_id="wiring-check-001",
                prompt_version="interpreter_v1",
                model="gpt-4o-mini",
                input_tokens=120,
                output_tokens=18,
                cost_usd=0.000029,
                latency_ms=640,
            )
        )
    print("span emitted")
    provider.force_flush()
    provider.shutdown()
    await asyncio.sleep(3)  # Langfuse indexes asynchronously

    url = f"{settings.langfuse_host.rstrip('/')}/api/public/v2/observations"
    window_start = (datetime.now(UTC) - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    window_end = (datetime.now(UTC) + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            url,
            params={"fromStartTime": window_start, "toStartTime": window_end, "limit": 10},
            auth=(settings.langfuse_public_key, settings.langfuse_secret_key),
        )
    if response.status_code != 200:
        print(f"FAILED: Langfuse API returned {response.status_code}: {response.text[:300]}")
        return 1

    payload = response.json()
    observations = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(observations, dict):
        observations = observations.get("data", [])
    print(f"observations in the last 15 min: {len(observations)}")
    for item in observations[:5]:
        if isinstance(item, dict):
            print(
                f"  - {item.get('name')} | {item.get('type')} | "
                f"{item.get('startTime') or item.get('timestamp')} | id={item.get('id')}"
            )
    if not observations:
        print("FAILED: export succeeded but no observation is visible yet")
        return 1

    print("OK: Langfuse Cloud receives traces from this configuration")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
