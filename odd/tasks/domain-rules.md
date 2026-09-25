# Feature: Domain and rules (`domain-rules`)

Status: **closed**
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

- [x] AC1: All §4.1 entities modeled + migrated; models match seed and API needs.
- [x] AC2: `evaluate_eligibility` implements all 8 rules with stable reason codes; positive/negative/boundary cases tested (exactly 12h rest, midnight-crossing shifts, DST change).
- [x] AC3: Hypothesis property tests prove: no overlap assignment and no rest violation can be produced for eligible results.
- [x] AC4: `rank_candidates` pure, weights configurable, score explanations, deterministic tie-break, no behavioral profiling.
- [x] AC5: State machine `transition(case, event)` covers every §4.2 edge; undefined transitions raise and are tested.
- [x] AC6: Port protocols + Clock/SystemClock/FakeClock defined; domain imports only protocols.
- [x] AC7: Deterministic seed: 25 employees, 2-week schedule, blocks, 2 managers; idempotent; `make seed` works against compose.
- [x] AC8: Coverage ≥ 95% in `app/domain/`; full suite green; ruff + mypy clean.
- [x] AC9: Work-unit commits recorded.

## Tasks

- [x] T1 — Entity models + migration 0002 (TDD on model invariants).
- [x] T2 — Eligibility engine + Hypothesis property tests (TDD).
- [x] T3 — Ranking engine (TDD).
- [x] T4 — State machine (TDD).
- [x] T5 — Ports + Clock + fakes (TDD on FakeClock behavior).
- [x] T6 — Full deterministic seed (TDD on determinism + idempotency) + wire `make seed`.
- [x] T7 — Coverage gate ≥95%, full verification, close.

## Verification evidence

- T1: RED (missing models) → GREEN; migration `0002_domain_entities` applied against live Postgres (15 tables confirmed via psql).
- T2: RED → GREEN 18 unit tests + 5 property tests (Hypothesis). Key discovery: CPython returns the *naive* difference when subtracting two aware datetimes sharing the same tzinfo object — wrong across DST transitions. All engine durations computed on UTC-normalized datetimes (`_absolute_seconds`).
- T3: RED → GREEN 9 tests; weights reorder correctly; ties break by id.
- T4: RED → GREEN 23 tests incl. 8 illegal pairs raising `UndefinedTransition` and a totality sweep test.
- T5: RED → GREEN: Clock port (System/Fake with advance/set), Scheduler/Channel/WorkforceAdapter/LLMClient protocols (runtime-checkable), InMemoryWorkforceAdapter.
- T6: RED → GREEN: 27 employees (kitchen 8, floor 9, bar 4, cleaning 2, office 2, supervisor 2 — "unos 25" per spec), 14-day schedule with rest-rule exercises (bar closer opens next morning), 4 unavailable blocks, 2 managers, deterministic IDs, idempotent re-run, `emp_id=phone` real-phone mapping (max 3). Verified live: seed_cli in container on a fresh volume.
- T7: coverage gate configured (`fail_under = 95`) — actual: **100%** on `app/domain/`. Final: 82/82 pytest, ruff clean, mypy strict clean.

## Commits

- `8b54198` feat(backend): full spec 4.1 entity models with migration 0002 verified against Postgres
- `e796b67` feat(backend): deterministic eligibility engine with stable reason codes and DST-safe absolute durations (TDD)
- `f29aec0` test(backend): Hypothesis property tests proving eligibility invariants (overlap, rest, codes)
- `218b028` feat(backend): weighted ranking engine with per-component explanations and deterministic tie-breaks (TDD)
- `643badb` feat(backend): pure rescue state machine covering every spec 4.2 edge with explicit side effects (TDD)
- `343c469` feat(backend): port protocols, Clock port with SystemClock/FakeClock and in-memory workforce adapter (TDD)
- seed commit + coverage gate commit: (see git log; docs commit below)

## Progress / Next step

Feature **domain-rules closed** (stacked on `feature/foundation`; rebase onto dev once foundation merges). Next per spec order: `rescue-orchestration` (Feature 2) — the contracts from this feature are now fixed.
