# Feature: Domain and rules (`domain-rules`)

Status: **in progress**
Branch: `feature/domain-rules` (stacked on `feature/foundation`; rebased onto dev once that merges)
Created: 2026-09-24

## Objective

Deliver spec Feature 1: the complete domain model (§4.1), eligibility engine
(§5.1), ranking engine (§5.2) and rescue state machine (§4.2) as **pure,
tested code**, plus the port contracts (`Channel`, `Scheduler`,
`WorkforceAdapter`, `LLMClient`, `Clock`) and the full deterministic demo
seed (§11).

## Problem / Why

This feature fixes the contracts everything else builds on ("Tras la feature
1, los contratos están fijados"). The seven invariants (§5.4) live here as
testable rules — they are never relaxed for any test or eval (spec §0 rule 4).

## Scope

In scope:
- SQLAlchemy models for all §4.1 entities + migration `0002`.
- Pure domain package (`app/domain/`): eligibility, ranking, state machine — no I/O, mypy strict.
- Port protocols + test doubles: `Clock` (System/Fake), `Scheduler`,
  `Channel`, `WorkforceAdapter`, `LLMClient` (Replay stub).
- Deterministic seed: 25 employees, roles per spec §11, 2-week schedule
  exercising every eligibility rule, availability blocks, 2 managers,
  optional `DEMO_REAL_PHONES`.
- Hypothesis property tests: rest periods and shift overlaps.
- Coverage ≥ 95% on `app/domain/`.

Out of scope: orchestrator orchestration logic (`rescue-orchestration`), LLM
interpreter (`llm-interpreter`), real channels.

## Constraints

- TDD mandatory (RED before GREEN), `uv run pytest`.
- Exclusion reasons carry stable machine codes with readable English messages.
- Ranking MUST NOT use response history or acceptance rates (§5.2).
- Deterministic tie-breaks (by id) everywhere.
- Domain never imports frameworks (FastAPI/Celery/SQLAlchemy stay out of `app/domain/`).

## Acceptance criteria

- [ ] AC1: All §4.1 entities modeled + migrated; models match seed and API needs.
- [ ] AC2: `evaluate_eligibility` implements all 8 rules with stable reason codes; positive/negative/boundary cases tested (exactly 12h rest, midnight-crossing shifts, DST change).
- [ ] AC3: Hypothesis property tests prove: no overlap assignment and no rest violation can be produced for eligible results.
- [ ] AC4: `rank_candidates` pure, weights configurable, score explanations, deterministic tie-break, no behavioral profiling.
- [ ] AC5: State machine `transition(case, event)` covers every §4.2 edge; undefined transitions raise and are tested.
- [ ] AC6: Port protocols + Clock/SystemClock/FakeClock defined; domain imports only protocols.
- [ ] AC7: Deterministic seed: 25 employees, 2-week schedule, blocks, 2 managers; idempotent; `make seed` works against compose.
- [ ] AC8: Coverage ≥ 95% in `app/domain/`; full suite green; ruff + mypy clean.
- [ ] AC9: Work-unit commits recorded.

## Tasks

- [ ] T1 — Entity models + migration 0002 (TDD on model invariants).
- [ ] T2 — Eligibility engine + Hypothesis property tests (TDD).
- [ ] T3 — Ranking engine (TDD).
- [ ] T4 — State machine (TDD).
- [ ] T5 — Ports + Clock + fakes (TDD on FakeClock behavior).
- [ ] T6 — Full deterministic seed (TDD on determinism + idempotency) + wire `make seed`.
- [ ] T7 — Coverage gate ≥95%, full verification, close.

## Verification evidence

(appended per task)

## Commits

(appended per commit)

## Progress / Next step

Next: T1.
