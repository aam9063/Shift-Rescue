# Feature: llm-runtime-wiring

**Status**: in progress
**Branch**: `feature/llm-runtime-wiring` (from `main` @ `38d26fc`)
**Spec references**: §6 (LLM usage points), §7.3 (Strands), §9.3 (degradation), §9.4 (observability), §12 (config)
**ADRs**: ADR-002 (Strands without autonomous loop), ADR-004 (provider selection, new)

## Problem

The LLM layer is implemented and tested, but **nothing wires it into the runtime**:

- `app/api/webhooks_twilio.py::get_twilio_service()` builds `RescueOrchestrator`
  without an `interpreter`, so the live API answers every WhatsApp message with
  the deterministic parser only.
- `app/agent/llm.py::StrandsLLMClient` exists but no production caller builds a
  real Strands model.
- `app/observability/tracing.py` can describe span attributes, but no
  `TracerProvider` is ever installed, so nothing is exported to Langfuse.
- `backend/.env` already contains `LLM_PROVIDER_INTERPRETER`, `NAN_*` and
  `LANGFUSE_*` values that **no code reads** (`Settings` never declares them).

## Goal

The live API interprets real WhatsApp messages with a real LLM and exports one
trace per rescue to Langfuse, without ever blocking a rescue when the provider
is slow, unavailable or unconfigured.

## Decisions (fixed, do not re-litigate)

1. **Provider: OpenAI first** (`LLM_PROVIDER=openai`, default), with `anthropic`
   and `bedrock` behind the same factory. NaN is not a separate provider: any
   OpenAI-compatible gateway is reached with `LLM_PROVIDER=openai` +
   `OPENAI_BASE_URL`. This also unblocks the pending real-model eval run.
2. **Fail closed, never crash** (§9.3): if the provider is disabled, the API key
   is missing, or the provider SDK is not installed, `build_interpreter()`
   returns `None`, logs one warning, and the orchestrator keeps using the
   deterministic parser. A rescue is never blocked by LLM configuration.
3. **Langfuse Cloud over OTLP/HTTP** (ADR-003): endpoint
   `<LANGFUSE_HOST>/api/public/otel/v1/traces` with Basic auth
   `base64(public_key:secret_key)`. No self-hosted Langfuse, no Langfuse SDK.
4. **Strands stays tool-less** (ADR-002): the model only interprets language;
   it never mutates state.
5. **Money is visible**: every LLM call reports `model`, tokens, latency and
   `cost_usd` (already in `StrandsLLMClient.last_usage`), with per-provider
   default prices overridable by env.

## Tasks

### T1 — Settings for the LLM provider and observability
Extend `Settings` (declared, typed, never read from untyped `os.getenv`):

| Setting | Default | Purpose |
| --- | --- | --- |
| `llm_provider` | `openai` | `openai \| anthropic \| bedrock \| none` |
| `llm_model_interpreter` | `""` | empty → provider default |
| `llm_temperature` | `0.0` | deterministic interpretation |
| `llm_max_tokens` | `500` | interpretation is short |
| `llm_timeout_seconds` | `10.0` | per call |
| `llm_confidence_threshold` | `0.75` | below → UNCLEAR path |
| `llm_price_input_per_1k` / `llm_price_output_per_1k` | `0.0` | `0.0` → provider default |
| `openai_api_key`, `openai_base_url` | `""`, `None` | OpenAI + compatible gateways |
| `anthropic_api_key`, `aws_region` | `""`, `eu-west-1` | alternative providers |
| `otel_exporter_otlp_endpoint` | `None` | explicit override |
| `langfuse_public_key`, `langfuse_secret_key`, `langfuse_host` | `""`, `""`, `https://cloud.langfuse.com` | traces |
| `sentry_dsn` | `""` | declared for parity with `.env` |

Derived read-only properties: `llm_enabled`, `traces_endpoint`,
`traces_auth_header`, `tracing_enabled`.

### T2 — Provider factory (`app/agent/factory.py`, new)
- `resolve_model_id(settings)` / `resolve_price(settings)`: provider defaults with
  env overrides. Defaults: openai `gpt-4o-mini` (0.00015 / 0.0006 per 1K),
  anthropic `claude-haiku-4-5` (0.0008 / 0.004), bedrock
  `eu.anthropic.claude-haiku-4-5-v1:0`.
- `build_model(settings)`: returns a Strands model
  (`OpenAIModel(client_args={"api_key":…, "base_url":…}, model_id=…, params={…})`,
  `AnthropicModel(…)`, `BedrockModel(…)`). Raises `LLMNotConfigured` with a clear
  message when credentials are missing.
- `build_interpreter(settings) -> MessageInterpreter | None`: the fail-closed
  entry point used by the API. Returns `None` (and logs `llm_disabled` with a
  reason, never a secret) for `provider=none`, missing credentials, or a missing
  provider SDK. Wraps `StrandsLLMClient` in `MessageInterpreter`.
- Strands is imported **only** here and in `llm.py` (ADR-002 boundary).

### T3 — Tracing to Langfuse (`app/observability/tracing.py` + `main.py`)
- `configure_tracing(settings, *, exporter=None, provider=None) -> bool`:
  idempotent; installs a global `TracerProvider` with resource attributes
  (`service.name`, `deployment.environment`) and a `BatchSpanProcessor` over the
  OTLP/HTTP exporter carrying the Langfuse Basic auth header. No-op returning
  `False` when `tracing_enabled` is false. Injectable exporter/provider keep
  tests hermetic (no network).
- `shutdown_tracing()`: flush + shutdown, safe to call when never configured.
- `main.py` lifespan: configure before `yield`, shutdown in `finally`.

### T4 — Runtime injection
- `webhooks_twilio.get_twilio_service()`: build the interpreter once via
  `build_interpreter(settings)` and pass it to `RescueOrchestrator`; log whether
  the LLM path is active.
- `evals/runner.py`: replace the Anthropic-hardcoded class with the shared
  factory, so evals and production use the same provider resolution; a missing
  configuration fails with an actionable message (not an ImportError).

### T5 — Dependencies
`backend/pyproject.toml`: declare what we now import directly —
`openai`, `opentelemetry-api`, `opentelemetry-sdk`,
`opentelemetry-exporter-otlp-proto-http`. `anthropic` stays an optional extra.

### T6 — Documentation
ADR-004 (provider selection + fail-closed policy), `assumptions.md` (A4 update),
`docs/runbook.md` (Langfuse key setup and verification), `docs/eval-report.md`
(real-model run is now wired), `backend/.env.example` (new variable names,
removing the never-read `LLM_PROVIDER_INTERPRETER` / `NAN_*` block).

## Acceptance criteria

1. With `LLM_PROVIDER=none` (or no key) the API starts, logs one warning, and
   answers with the deterministic parser — no exception, no blocked rescue.
2. With a valid `OPENAI_API_KEY`, `get_twilio_service()` builds an orchestrator
   whose interpreter is a `MessageInterpreter` over `StrandsLLMClient`, and an
   inbound WhatsApp message is interpreted by the model.
3. With Langfuse keys present, one trace per rescue appears in Langfuse Cloud
   with model, tokens, latency and cost; with keys absent, tracing is a no-op.
4. No secret is ever logged or committed; `Settings` is the only reader of
   environment configuration.
5. `uv run pytest -q`, `uv run ruff check .`, `uv run mypy app` clean.

## Verification evidence

_Pending — recorded as each task closes._
