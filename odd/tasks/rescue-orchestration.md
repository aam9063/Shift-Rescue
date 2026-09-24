# Feature: Rescue orchestration (`rescue-orchestration`)

Status: **in progress**
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
- [ ] T3 — Acceptance resolution with row-lock revalidation + approval path (TDD).
- [ ] T4 — Waves, timeouts and escalation via SimScheduler (TDD).
- [ ] T5 — Quiet hours + manager location link migration (TDD).
- [ ] T6 — Race test on real PostgreSQL + §5.5 integration suite + close.

## Verification evidence

- T1: RED → GREEN. Parser: 30 tests (confirm/decline vocabulary incl. emoji and digits, absence phrasing with accent/case normalization, retraction, ambiguity → UNCLEAR never acts, health details never extracted). 112/112 suite, lint clean. Commit `c1f685a`.
- T2: RED → GREEN 6 orchestrator tests. New: `MockWorkforceAdapter` (SQLAlchemy-backed, tz-normalizing), health redaction (`redact_if_health`), es-ES templates module, migration `0003` (`manager.location_ids`). Covered: report → OPEN case + absence_confirm (no manager notice, no offers yet); confirm → OFFERING + 3 offers wave 1 + HRIS absent + audit RESCUE_OPENED/OFFER_SENT + manager notified; duplicate provider_message_id processed once; two shifts → ask_which_shift; confirm without pending → out_of_scope; health text stored as `[redacted: health details]`. 118/118, mypy strict clean. Commit `a0fe30b`.
  - Design note: OPEN state = "detected, awaiting explicit confirmation"; confirmation drives OPEN→OFFERING (spec: confirm before opening the rescue).

## Commits

(appended per commit)

## Progress / Next step

T1-T2 closed. Next: T3 — acceptance resolution with row-lock revalidation + approval path.
