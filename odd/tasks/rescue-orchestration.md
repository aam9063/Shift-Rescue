# Feature: Rescue orchestration (`rescue-orchestration`)

Status: **closed**
Branch: `feature/rescue-orchestration` (stacked on `feature/domain-rules`)
Created: 2026-09-24

## Objective

Deliver spec Feature 2: `RescueOrchestrator`, `SimScheduler`,
`SimulatedChannel`, DB-backed `MockWorkforceAdapter`, waves, deadlines,
quiet hours, concurrency and idempotency. The LLM interpreter is replaced by
a deterministic parser for this feature.

## Problem / Why

This is the execution core: detecting an absence, opening the rescue,
computing candidates, offering in waves and resolving acceptances — with the
§5.4 invariants enforced under real concurrency.

## Scope

In scope:
- Deterministic message parser (`app/domain/parser.py`) replacing the LLM.
- `RescueOrchestrator` service: inbound handling (idempotent by provider_message_id), absence confirmation flow, case opening (OPEN → OFFERING), candidate computation (eligibility + ranking), wave sending with expiry, acceptance resolution with re-validation under row lock, escalation paths.
- `SimScheduler` (in-memory, FakeClock-driven) and `SimulatedChannel` (records messages, no external calls).
- `MockWorkforceAdapter` backed by the DB (workforce tables via SQLAlchemy).
- Quiet hours (§5.3) and deadline rules (§5.3).
- Manager↔location link (migration 0003: `manager.location_ids` JSON).
- Integration tests (§5.5 edge cases) incl. the acceptance race on real PostgreSQL.

Out of scope: LLM interpreter (`llm-interpreter`), Twilio, dashboard WebSocket push details.

## Constraints

- TDD mandatory; the seven invariants (§5.4) are never relaxed.
- Inbound webhook path: no LLM, respond fast; heavy work in tasks.
- External effects happen after state is persisted.
- Every state change writes `AuditEvent`.

## Acceptance criteria

- [ ] AC1: Deterministic parser recognizes the degraded-mode vocabulary and absence phrasing; ambiguous → clarification, never action.
- [ ] AC2: Full happy path: report → confirmation → case OPEN → candidates → OFFERING + first wave; manager notified; HRIS marked absent; audit trail written.
- [ ] AC3: Acceptance revalidates eligibility under `SELECT ... FOR UPDATE`; first valid acceptance wins; loser receives `offer_already_covered`.
- [ ] AC4: Waves advance on expiry until waves exhausted or deadline; escalation on deadline/empty candidates.
- [ ] AC5: Quiet hours block offers except for shifts starting within 3h.
- [ ] AC6: Duplicate provider messages processed once (idempotency).
- [ ] AC7: Conditional accept / overtime → AWAITING_APPROVAL with ApprovalRequest; approval resolves to COVERED/PARTIALLY_COVERED.
- [ ] AC8: §5.5 edge-case integration tests green, including the acceptance race on real PostgreSQL.
- [ ] AC9: Work-unit commits recorded.

## Tasks

- [x] T1 — Deterministic parser (TDD).
- [x] T2 — Orchestrator: inbound handling, confirmation flow, case opening, first wave (TDD, sqlite).
- [x] T3 — Acceptance resolution with row-lock revalidation + approval path (TDD).
- [x] T4 — Waves, timeouts and escalation via SimScheduler (TDD).
- [x] T5 — Quiet hours + manager location link migration (TDD).
- [x] T6 — Race test on real PostgreSQL + §5.5 integration suite + close.

## Verification evidence (T3-T6)

- T3: acceptance 8 tests (`5c36e80`) — COVERED on unconditional accept (others CANCELLED, HRIS assigned, templates sent), loser gets already_covered, overtime → AWAITING_APPROVAL + ApprovalRequest, decide_approval approves/rejects, decline, withdrawal reopens, cancel_rescue request.
- T4+T5: 12 tests (`98bebf6`) — SimScheduler drives wave 2 on expiry (previous waves stay alive per §5.3), WAVES_EXHAUSTED/DEADLINE_REACHED escalate with manager notice, approval timeout → OFFERING (request expired), late acceptance after escalation → AWAITING_APPROVAL, quiet hours queue offers to 07:00 (invariant 4) with wave_timeout deferring to the queued send. Domain helper `offers_allowed` + `next_quiet_end` with unit tests.
- T6: integration on real PostgreSQL (`tests/integration/test_race.py`): acceptance race via asyncio.gather → exactly one ACCEPTED offer, single COVERED case, loser CANCELLED + already_covered, HRIS consistent; duplicate provider_message_id idempotent on PG.

Final: 141 passed with integration (2 tests on real PG), 139/139 unit-only (integration skips without DATABASE_URL); coverage 99.6% (gate 95%); ruff + mypy strict clean.

§5.5 mapping: race → integration; dup message → unit+integration; out-of-scope → unit; ambiguity → unit; manipulation → parser UNCLEAR (unit); withdraw → unit; retract/cancel → unit; late acceptance → unit; HRIS failure & LLM-down → `resilience` feature.

## Commits

- `c1f685a` feat(backend): deterministic message parser for degraded-mode orchestration (TDD)
- `a0fe30b` feat(backend): RescueOrchestrator core with idempotent inbound, confirmation flow, case opening and first wave (TDD)
- `5c36e80` feat(backend): offer acceptance with FOR UPDATE revalidation, approval decisions, decline and withdrawal paths (TDD)
- `8874939` feat(backend): SimScheduler waves, timeouts, escalation and quiet-hours gating (TDD)
- race/integration commit: (see git log)

## Progress / Next step

Feature **rescue-orchestration closed**. Next per spec order: `llm-interpreter` (Feature 3) — Strands-based structured interpretation replacing the deterministic parser, or parallel-track `manager-dashboard` slices.
