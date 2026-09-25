# ADR-004: LLM provider selection — OpenAI first, fail-closed to the parser

Status: accepted
Date: 2026-09-25
Deciders: product owner + FDE
Related: spec §6, §7.3, §9.3, §9.4, ADR-002, ADR-003, `docs/assumptions.md` A4,
Feature `llm-runtime-wiring`

## Context

The LLM layer was implemented and unit-tested (prompt, structured output,
validation retry, confidence threshold, circuit breaker, cost metering), but no
production code path built a real model: `get_twilio_service()` assembled the
orchestrator with `interpreter=None`, so every live WhatsApp message was
answered by the deterministic parser. The two eval providers also hardcoded a
single vendor, and `backend/.env` carried `LLM_PROVIDER_INTERPRETER`, `NAN_*`
and `LANGFUSE_*` values that no code read.

Three forces decided the shape of this ADR:

1. **Vendor dependency is a product risk**, not an implementation detail: the
   client must be able to change model provider without touching domain code.
2. **A rescue must never be blocked by an LLM problem** (spec §9.3). A missing
   API key, an uninstalled SDK or a dead provider is a *degradation*, not a
   crash.
3. **Cost and latency must be visible** from day one, or the operating limits
   in spec §9 cannot be enforced.

The product owner chose **OpenAI** as the first provider (existing credits, low
latency, strong structured-output support) over the previously configured
OpenAI-compatible gateway (NaN), which stays reachable without a code change.

## Decision

| Aspect | Decision | Rationale |
|---|---|---|
| Default provider | `LLM_PROVIDER=openai`, model `gpt-4o-mini` | Credits available, low p95 latency, reliable structured output; cheap enough for the demo volume. |
| Provider surface | `openai`, `anthropic`, `bedrock` behind one factory (`app/agent/factory.py`) | Swapping provider is one environment variable; the domain keeps depending only on the `LLMClient` protocol. |
| OpenAI-compatible gateways | Not a separate provider: `LLM_PROVIDER=openai` + `OPENAI_BASE_URL` | NaN, Azure-style gateways and local proxies all speak the OpenAI API; a second code path would be duplicated logic with no added guarantee. |
| Credential resolution | `Settings` only (`Pydantic Settings`), never `os.getenv` at call sites | One typed place to audit; `extra="ignore"` makes stale variables harmless. |
| Failure policy | **Fail closed to the deterministic parser**: `build_interpreter()` returns `None` and logs one warning | A misconfigured or unreachable LLM must degrade quality, never availability (spec §9.3). |
| Agent shape | Strands `Agent` with **no tools** and `structured_output_model=Interpretation` | ADR-002: the LLM interprets language and composes text; it never mutates state. |
| Tracing | OpenTelemetry → **Langfuse Cloud** over OTLP/HTTP, `configure_tracing()` idempotent, endpoint/keys from `Settings` | ADR-003: no self-hosted Langfuse. Strands emits native model spans, so no manual instrumentation is needed. |
| Secrets | Never logged, never returned, never committed; only endpoint host and provider/model id are logged | The repository is public and demo logs are shared with reviewers. |
| Cost | Per-provider default prices per 1K tokens, overridable by `LLM_PRICE_*_PER_1K` | Cost per rescue must be auditable in Langfuse and in the Ops screen. |

### Rejected alternatives

- **Keep the deterministic parser as the only live path** — safest, but the
  product's core promise (understanding free-form WhatsApp Spanish) would be
  false in the demo.
- **A separate `nan` provider implementation** — duplicated client
  construction for an API-compatible endpoint; `OPENAI_BASE_URL` covers it.
- **Fail-fast on missing credentials (crash at boot)** — turns a configuration
  mistake into an outage; rejected in favour of one warning plus degradation.
- **Langfuse SDK instead of OpenTelemetry** — a second instrumentation path for
  the same data, and it would not capture Strands' own spans.
- **Instrument model calls manually** — Strands already emits spans; manual
  wrappers would drift from the SDK and add cost per call.

## Consequences

- Positive: provider swap is one variable; the API boots without any provider
  SDK installed; live interpretation, cost and latency become observable;
  evals and production resolve the provider identically, so an eval result
  describes the shipped configuration.
- Negative: a missing key degrades silently to the parser — mitigated by the
  `llm_disabled` warning, the `describe_provider()` log line at wiring time and
  the `llm_path` field on the startup log.
- Ambiguity of the deterministic parser is now a *fallback behaviour*, so the
  eval suite must keep covering both paths (`llm_down` scenarios stay).
- Prices are configuration, not truth: a provider price change requires a
  settings update, and the numbers are estimates for cost control, not billing.
