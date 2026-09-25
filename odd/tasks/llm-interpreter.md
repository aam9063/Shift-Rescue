# Feature: LLM interpreter (`llm-interpreter`)

Status: **closed**
Branch: `feature/llm-interpreter` (stacked on `feature/rescue-orchestration`)
Created: 2026-09-24

## Objective

Deliver spec Feature 3: `LLMClient` over the Strands Agents SDK (version
**pinned: 1.56.0**, verified against its docs) with traces, cost, retries and
circuit breaker; the message interpreter with validated structured output;
prompts v1 (es-ES few-shot); golden set and eval harness with thresholds;
ADR documenting the no-autonomous-loop decision.

## Problem / Why

The deterministic parser (Feature 2) only handles an explicit vocabulary.
Real employees write loosely ("igual si luego te digo", "k", audios
transcritos). The interpreter must classify intent with validated structured
output — the LLM proposes, the domain disposes (spec §6).

## Scope

In scope:
- `strands-agents==1.56.0` pinned (Pydantic structured output via
  `Agent(structured_output_model=...)`, metrics from `AgentResult`, native
  OpenTelemetry — API verified in the official docs today).
- `agent/schemas.py`: `Interpretation` Pydantic model per spec §6.2.
- `agent/interpreter.py`: interpreter with validation, one retry including
  the validation error, fallback `UNCLEAR`, confidence threshold (0.75).
- `agent/prompts/interpreter_v1.md`: stable system block + es-ES few-shot.
- `agent/llm.py`: `LLMClient` wrapper — model config, timeout, retries,
  circuit breaker, token/cost metering, trace attributes
  (`rescue_id`, `prompt_version`). Domain never imports Strands directly.
- Evals: `evals/golden/interpreter_golden.jsonl` (150+ labeled messages),
  `evals/runner.py`, `evals/thresholds.yaml`, report in `evals/reports/`.
- ADR-002: Strands without the autonomous loop; parser stays as degraded
  fallback (§9.3).
- Orchestrator wiring: interpreter first, parser fallback on breaker open /
  low confidence.

Out of scope: NaN/Bedrock comparison (`make eval-models` arrives with the
evals-observability feature), real Twilio, dashboard screens.

## Constraints

- Hermetic tests: no API key needed; the real-model golden run requires
  `ANTHROPIC_API_KEY` and is executed by the eval runner on demand.
- Invariant 7: health details redacted before persistence (already enforced).
- The LLM has no tools that mutate state; domain validates every output.

## Acceptance criteria

- [x] AC1: `Interpretation` schema validated with Pydantic; invalid LLM
      output retried once with the error included, then `UNCLEAR`.
- [x] AC2: `StrandsLLMClient` implements the `LLMClient` protocol with
      timeout, retries, circuit breaker and token/cost capture; unit-tested
      with injected fakes.
- [x] AC3: Prompts v1 versioned in `agent/prompts/`, version recorded in
      every interpretation.
- [x] AC4: Golden set ≥ 150 labeled messages covering §8.1 categories.
- [x] AC5: Eval runner computes intent accuracy, F1 per intent, health
      detection rate, latency and cost; report written to `evals/reports/`;
      offline baseline (deterministic parser) runs without a key.
- [x] AC6: Orchestrator uses the interpreter with parser fallback; degraded
      mode path tested.
- [x] AC7: ADR-002 written.
- [x] AC8: Work-unit commits recorded.

## Tasks

- [x] T1 — Deps pinned + Interpretation schema + interpreter core (TDD).
- [x] T2 — Prompts v1 + StrandsLLMClient wrapper with breaker/metering (TDD).
- [x] T3 — Golden set + eval runner + offline baseline report.
- [x] T4 — ADR-002 + orchestrator wiring (TDD) + close.

## Verification evidence

- T1: RED → GREEN 8 tests — schema rejects unknown intents/out-of-range confidence; interpreter validates, retries once with the validation error, falls back to UNCLEAR on second failure or provider exception (degrades without retry), low confidence returned untouched for the caller. `e009dbc`.
- T2: RED → GREEN 6 tests — breaker opens at N consecutive failures and resets after the window, open circuit fails fast without agent call, transient failure retried once, timeout enforced with asyncio.wait_for, usage/cost captured from AgentResult metrics, prompt carries message + rescue_id + pending context + validation-error retry note. Prompts v1 with es-ES few-shot incl. health, typos, abbreviations and manipulation. `341646f`.
- T3: golden set generator → 150 labeled rows (§8.1 categories: reports with health, confirms, accepts, declines, 20 conditionals with time extraction, retracts, withdrawals, 15 ambiguous, questions, smalltalk, manipulation, english). Runner with parser/interpreter providers, F1 per intent, health detection, conditional-time accuracy, report JSON in evals/reports/. Offline baseline: parser accuracy 0.3733 (informational floor — the real-model threshold run ≥0.92 requires ANTHROPIC_API_KEY, documented). `0df0321`.
- T4: wiring RED → GREEN 5 tests — LLM intents routed (accept/confirm/report/conditional→partial-coverage approval/withdraw/retract), UNCLEAR → single clarification then redirect, CircuitOpenError → parser fallback with zero LLM calls, no-interpreter keeps parser behavior; outbound clarification persisted for dedupe. ADR-002 written. `402ad19`.

Final: 158 passed (2 skipped integration without DATABASE_URL); ruff + mypy strict clean.

## Commits

- `e009dbc` feat(backend): Interpretation schema and message interpreter with validation retry and UNCLEAR fallback (TDD)
- `341646f` feat(backend): StrandsLLMClient with circuit breaker, timeout, retries and cost metering; prompts v1 (TDD)
- `0df0321` feat(evals): golden set (150 labeled messages), eval runner with thresholds and offline parser baseline report
- `402ad19` feat(backend): orchestrator routes LLM interpretations with parser fallback, conditional approvals and clarification dedupe (TDD)

## Progress / Next step

Feature **llm-interpreter closed**. Real-model golden run (≥0.92 accuracy, ≥0.95 health detection) pending `ANTHROPIC_API_KEY` — documented as an assumption; `uv run python evals/runner.py --provider interpreter` when available. Next per spec order: `evals-observability` (Feature 4) or `manager-dashboard` slices (parallelizable).
