# Feature: LLM interpreter (`llm-interpreter`)

Status: **in progress**
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

- [ ] AC1: `Interpretation` schema validated with Pydantic; invalid LLM
      output retried once with the error included, then `UNCLEAR`.
- [ ] AC2: `StrandsLLMClient` implements the `LLMClient` protocol with
      timeout, retries, circuit breaker and token/cost capture; unit-tested
      with injected fakes.
- [ ] AC3: Prompts v1 versioned in `agent/prompts/`, version recorded in
      every interpretation.
- [ ] AC4: Golden set ≥ 150 labeled messages covering §8.1 categories.
- [ ] AC5: Eval runner computes intent accuracy, F1 per intent, health
      detection rate, latency and cost; report written to `evals/reports/`;
      offline baseline (deterministic parser) runs without a key.
- [ ] AC6: Orchestrator uses the interpreter with parser fallback; degraded
      mode path tested.
- [ ] AC7: ADR-002 written.
- [ ] AC8: Work-unit commits recorded.

## Tasks

- [ ] T1 — Deps pinned + Interpretation schema + interpreter core (TDD).
- [ ] T2 — Prompts v1 + StrandsLLMClient wrapper with breaker/metering (TDD).
- [ ] T3 — Golden set + eval runner + offline baseline report.
- [ ] T4 — ADR-002 + orchestrator wiring (TDD) + close.

## Verification evidence

(appended per task)

## Commits

(appended per commit)

## Progress / Next step

Next: T1.
