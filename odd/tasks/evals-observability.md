# Feature: Evals harness and observability (`evals-observability`)

Status: **closed**
Branch: `feature/evals-observability` (stacked on `feature/llm-interpreter`)
Created: 2026-09-24

## Objective

Deliver spec Feature 4: `ShiftRescueTarget` adapter, scenario runner with
FakeClock/SimScheduler/SimulatedChannel, simulated employee personas,
evaluators, red-team scenarios, CI thresholds, and full observability:
OpenTelemetry export to **Langfuse Cloud** (user decision — see
`docs/assumptions.md` A4), structured logs, redaction, alerts.

## Problem / Why

The evals are the piece that differentiates the project (spec §8): they prove
the invariants hold under simulated full rescues and block CI on quality
regressions. Observability makes every rescue traceable end-to-end (one trace
per rescue, grouped in Langfuse) and alerts surface stuck rescues and
degradation.

## Scope

In scope:
- `ShiftRescueTarget`: exposes the full system to the eval harness — inject
  inbound message via SimulatedChannel, advance FakeClock, return outbound
  messages and rescue events.
- Scenario runner: YAML scenarios (spec §8.2 minimum set) + personas
  (deterministic scripts for timing-sensitive personas; LLM-simulated
  personas only when a key is present).
- Evaluators: invariant checks (deterministic code — never an LLM judge),
  scenario assertions (final_state, covering employee, templates).
- Thresholds gate CI (`evals/thresholds.yaml` extended with scenario gates).
- Observability: OTLP export to Langfuse Cloud via env vars (no Langfuse
  containers — user decision A4), structlog JSON logs with rescue_id/trace_id,
  phone masking, alerts (stuck rescue, LLM error rate, delivery failures).

Out of scope: Strands Evals user simulators (optional enhancement; the spec
allows our own personas), model comparison `make eval-models` (its table
arrives when a key is available; the command lands here).

## Constraints

- Invariant violations are deterministic checks — never an LLM judge (§8.3).
- Scenarios run hermetically: FakeClock, in-memory scheduler and channel;
  no network. Real-LLM personas skip without keys.
- Every scenario asserts 0 invariant violations (§8.3 blocks CI).

## Acceptance criteria

- [x] AC1: `ShiftRescueTarget` runs a full rescue scenario in milliseconds
      (report → confirm → waves → resolution) driven by FakeClock.
- [x] AC2: All spec §8.2 minimum scenarios defined in YAML and passing with
      0 invariant violations.
- [x] AC3: Runner produces a per-scenario report (markdown + JSON) with
      invariant checks, message audit and timing.
- [x] AC4: OTel traces export to Langfuse Cloud when LANGFUSE_* env vars are
      set; one trace per rescue grouped by rescue_id.
- [x] AC5: structlog JSON logs carry rescue_id/trace_id; phone numbers
      masked; health details never present.
- [x] AC6: Alerts computed (stuck rescue, LLM error rate, delivery failures,
      cost) and surfaced in structured logs (Ops screen consumption later).
- [x] AC7: `make eval` runs the scenario suite locally; CI-ready command.
- [x] AC8: Work-unit commits recorded.

## Tasks

- [x] T1 — ShiftRescueTarget + scenario loader + invariants checker (TDD).
- [x] T2 — Spec §8.2 minimum scenarios in YAML, all green (TDD).
- [x] T3 — OTel → Langfuse Cloud export + log enrichment + phone masking (TDD).
- [x] T4 — Alerts module + report generation + `make eval` + close.

## Verification evidence

- T1: RED → GREEN. `ShiftRescueTarget.create(...)` mounts the full stack (FakeClock, SimScheduler, SimulatedChannel, DB-backed mock HRIS) on a temp-file SQLite; `run_scenario(spec)` drives report → auto-confirm → personas → manager decisions → scheduled jobs; deterministic `check_invariants(snapshot)` validates all 7 invariants (§5.4) — never an LLM judge. `333eaf6`.
- T2: 14 YAML scenarios (spec §8.2 minimum set) all passing with 0 invariant violations: quick coverage, second wave, no candidates, all decline, acceptance race, conditional approved/rejected, withdraw-after-accept, absent retracts (cancel approval), shift already started, quiet-hours deferral, HRIS failure escalation (retry ×3 → TECHNICAL_FAILURE), LLM-down degraded (parser fallback), manipulation + health redaction. New: HRIS failure injection in the mock adapter, manager decision steps in the runner. `0e55beb`.
- T3: `offers_allowed` evaluated in the location timezone (quiet hours are wall-clock); phone masking; OTel config helpers for Langfuse Cloud (OTLP endpoint + LANGFUSE_* env — no containers, user decision A4). `efcb361`.
- T4: alert rules (stuck rescue, LLM error rate >5%, low confidence >20%, delivery failures, cost) as pure tested functions; `make eval` runs the scenario suite + golden baseline.

Final: 189/189 unit (integration 2/2 on real PG with DATABASE_URL); ruff + mypy strict clean.

## Commits

- `333eaf6` feat(backend): ShiftRescueTarget eval harness, deterministic invariant checker and YAML scenario runner (TDD)
- `0e55beb` feat(backend): spec 8.2 scenario suite, OTel-ready quiet-hour tz handling and HRIS failure escalation (TDD)
- `efcb361` feat(backend): observability wiring — OTLP to Langfuse Cloud, phone masking, alert rules and make eval (TDD)

## Progress / Next step

Feature **evals-observability closed**. Next per spec order: `manager-dashboard` (Feature 5) — nine screens on the existing token system; then `whatsapp-channel` (6), `resilience` (7), `deploy-delivery` (8, with ADR-003 including the Langfuse Cloud decision).
