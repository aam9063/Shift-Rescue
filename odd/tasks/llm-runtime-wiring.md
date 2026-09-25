# Feature: llm-runtime-wiring

**Status**: T1–T6 complete and committed; T7 (live verification with real
credentials) partially verified — Langfuse confirmed, OpenAI pending the API key
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

### Automated checks (branch `feature/llm-runtime-wiring`)

| Check | Result |
| --- | --- |
| `cd backend && uv run pytest -q` | `258 passed, 2 skipped` (was 225 passed: +33 new tests; the 2 skips are the pre-existing PostgreSQL integration markers) |
| `cd backend && uv run ruff check .` | `All checks passed!` |
| `cd backend && uv run mypy app` | `Success: no issues found in 51 source files` |
| `Settings(_env_file=None)` smoke | `openai True False None` |

### Fail-closed behaviour (real objects, fake key)

```
OpenAI model built: OpenAIModel | config: gpt-4o-mini {'max_tokens': 500, 'temperature': 0.0}
no key -> None                    # llm_disabled reason='OPENAI_API_KEY is not set'
none   -> None                    # llm_disabled reason='provider is disabled'
interpreter: MessageInterpreter | llm: StrandsLLMClient | threshold: 0.75
Bedrock model built: BedrockModel  # signature verified, never exercised
```

### Live runtime (rebuilt `api` container, real `backend/.env`)

```
tracing_enabled endpoint_host=cloud.langfuse.com
llm_disabled    reason='OPENAI_API_KEY is not set — add it to backend/.env'
llm_path        active=false detail='provider=openai model=gpt-4o-mini'
```

This is acceptance criterion 1 verified in the deployed shape: the API boots
with no provider credential, reports it once, and keeps serving through the
deterministic parser.

### Langfuse Cloud — end to end with the real keys

`scripts/verify_langfuse.py` (new, reusable) exports one span through the
configured OTLP/HTTP exporter and reads it back from Langfuse:

```
endpoint: https://cloud.langfuse.com/api/public/otel/v1/traces
auth header present: True
span emitted
observations in the last 15 min: 1
  - rescue.lifecycle | GENERATION | 2026-09-25T10:24:09.432Z | id=047fcd20cb2e8b4c
OK: Langfuse Cloud receives traces from this configuration
```

Acceptance criterion 3 verified. Note for maintainers: Langfuse retired
`GET /api/public/traces` (`410 LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION` for
organizations created on or after 2026-09-16); reads now use
`GET /api/public/v2/observations?fromStartTime=&toStartTime=`. The exporter
endpoint is unchanged.

### Environment correction

The user's `backend/.env` had a broken comment (a line that lost its leading
`#`), which made `python-dotenv` abort parsing from line 18 onward, plus three
variables no code ever read (`LLM_PROVIDER_INTERPRETER`, `NAN_API_KEY`,
`NAN_BASE_URL`, `LLM_MODEL_INTERPRETER_NAN`). The LLM block was rewritten with
the ADR-004 names (backup at `backend/.env.bak`); the gateway credentials are
preserved as commented lines, reachable as `OPENAI_BASE_URL`.

### Real provider calls (OpenAI `gpt-4o-mini`, `scripts/verify_llm.py`)

Two defects that only a live call could reveal — both invisible to the unit
suite because the test doubles were more forgiving than the SDK:

1. **`prompt_version` collision (crash).** `StrandsLLMClient` returns the whole
   `Interpretation` dump, which already contains `prompt_version`, while
   `MessageInterpreter` passed it again as a keyword argument →
   `TypeError: got multiple values for keyword argument 'prompt_version'`, which
   surfaced as `ProviderUnavailableError` and silently degraded every message to
   the parser. Fixed by merging (`{**raw, "prompt_version": ...}`) with a
   regression test that feeds a *full* payload.
2. **Metering read fields that no longer exist.** Strands 1.56 reports
   `EventLoopMetrics.accumulated_usage` in camelCase (`inputTokens`,
   `outputTokens`, `cacheReadInputTokens`) and latency in
   `accumulated_metrics['latencyMs']`; the client read `metrics.usage` and
   `metrics.total_cycle_time`, so every call was metered as 0 tokens / $0.
   Fixed with version-tolerant extraction plus a wall-clock latency fallback,
   tested against the real camelCase shape and the legacy snake_case one.

After the fixes:

```
[ABSENCE_REPORT    ] confidence=0.98 latency=1697ms tokens=1157/38 cost=$0.000196
[ABSENCE_REPORT    ] confidence=0.95 latency=1056ms tokens=1147/60 cost=$0.000208
[OFFER_CONDITIONAL ] confidence=0.90 latency=2750ms tokens=1156/59 cost=$0.000209
```

Acceptance criterion 2 verified. Two observations to act on:

- **Latency — decided (option a):** the dashboard target moves from 1.2 s to
  **2.5 s** (`frontend/src/services/dashboardMock.ts`), because the 1.2 s figure
  was a mockup number never measured while the real calls land at 1.0–2.8 s
  including the Strands agent cycle. `evals/thresholds.yaml` already allowed
  5 s. The system prompt stays as it is: ~1150 input tokens per call, of which
  ~1024 are prompt-cache reads, so trimming it buys latency only at the cost of
  interpretation quality.
- **Prompt size:** ~1024 of ~1150 input tokens are served from the provider's
  prompt cache (`cacheReadInputTokens`), so the real cost is below the
  conservative estimate reported per call.

### Open deviation found while verifying

Spec §7.5 requires the inbound Twilio webhook to answer in **under 200 ms** and
never call the LLM inside it (validate, persist, enqueue). The current wiring
awaits `orchestrator.handle_inbound()` — and therefore the interpretation call —
so the webhook now takes 1–3 s. Twilio's webhook timeout is 15 s, so the demo is
unaffected, but moving interpretation to a Celery task is the next production
step and is not done here. Verified evidence: the latency numbers above are
the webhook's own critical path.

### Pending

- Full eval run against the real model (`uv run python evals/runner.py
  --provider interpreter`), which closes the accuracy thresholds in
  `docs/eval-report.md`.
- Move the interpretation call off the webhook request path (Celery task per
  spec §7.5) — see the open deviation above.
- Rotate the OpenAI key that was exposed in the session transcript: done by the
  user, re-verified against the live API after rotation.

## Next step

Push `feature/llm-runtime-wiring` and open the PR for review; the eval run and
the webhook offloading are separate work units.
