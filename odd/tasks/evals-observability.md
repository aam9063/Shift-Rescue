# Feature: Evals harness and observability (`evals-observability`)

Status: **in progress**
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

- [ ] AC1: `ShiftRescueTarget` runs a full rescue scenario in milliseconds
      (report → confirm → waves → resolution) driven by FakeClock.
- [ ] AC2: All spec §8.2 minimum scenarios defined in YAML and passing with
      0 invariant violations.
- [ ] AC3: Runner produces a per-scenario report (markdown + JSON) with
      invariant checks, message audit and timing.
- [ ] AC4: OTel traces export to Langfuse Cloud when LANGFUSE_* env vars are
      set; one trace per rescue grouped by rescue_id.
- [ ] AC5: structlog JSON logs carry rescue_id/trace_id; phone numbers
      masked; health details never present.
- [ ] AC6: Alerts computed (stuck rescue, LLM error rate, delivery failures,
      cost) and surfaced in structured logs (Ops screen consumption later).
- [ ] AC7: `make eval` runs the scenario suite locally; CI-ready command.
- [ ] AC8: Work-unit commits recorded.

## Tasks

- [ ] T1 — ShiftRescueTarget + scenario loader + invariants checker (TDD).
- [ ] T2 — Spec §8.2 minimum scenarios in YAML, all green (TDD).
- [ ] T3 — OTel → Langfuse Cloud export + log enrichment + phone masking (TDD).
- [ ] T4 — Alerts module + report generation + `make eval` + close.

## Verification evidence

(appended per task)

## Commits

(appended per commit)

## Progress / Next step

Next: T1.
