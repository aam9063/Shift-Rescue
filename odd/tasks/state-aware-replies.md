# Feature: state-aware-replies

**Status**: in progress
**Branch**: `feature/dashboard-live`
**Spec references**: §5.4 (confirmation), §5.5 (ambiguity and redirects), §6.6 (message templates)

## Problem

When the agent cannot act on a message it answers with one generic line:

> "Hola, soy el asistente de turnos de La Terraza del Puerto y solo gestiono
> avisos de ausencia y coberturas. Para cualquier otra cosa, contacta con tu
> encargado."

For an employee who **already has a live case** that sentence is the opposite of
the truth. Verified in a real WhatsApp thread: the employee reported an absence,
the agent asked for confirmation, the employee's next reply did not match
anything pending (the state had moved on), and the agent answered "I only handle
absences and coverage" — while the absence was registered and being covered.
Same for a candidate who has an outstanding offer: an unclear reply ends in the
same generic redirect instead of a reminder that the offer is waiting.

## Decisions (fixed, do not re-litigate)

1. **One choke point.** `_send_out_of_scope` is where every unresolved message
   lands, so the state check lives there: the redirect becomes state-aware for
   everyone, with no per-caller duplication.
2. **Priority follows what the employee can act on**: an outstanding offer to
   that employee first (they are a candidate and an answer is expected), then
   their own live case — awaiting their confirmation (`OPEN`), being covered
   (`OFFERING`), or waiting for the manager (`AWAITING_APPROVAL`).
3. **Reuse the wording the employee already knows.** The `OPEN` case is answered
   with the existing `absence_confirm` question rather than a new phrasing; only
   genuinely new states get new templates.
4. **Terminal cases get the generic redirect.** A covered, cancelled or escalated
   case is closed; nothing is pending, so a state message would be misleading.
5. **Spanish, es-ES, same register as the rest of §6.6** — these are
   employee-facing WhatsApp messages, never UI copy.
6. **No LLM involvement**: templates stay deterministic.

## Tasks

### T1 — Templates (`app/channels/templates.py`)
`state_searching_coverage` (their absence is registered and being covered),
`state_awaiting_approval` (their coverage waits for the manager) and
`offer_reminder` (an offer is still open, answer SÍ/NO or give hours). Keep the
existing `absence_confirm` for the `OPEN` case and `out_of_scope` unchanged.

### T2 — State-aware redirect (`app/services/orchestrator.py`)
In `_send_out_of_scope`, resolve the employee's situation and pick the message:
outstanding offer → `offer_reminder`; live case `OPEN` → `absence_confirm`;
`OFFERING` → `state_searching_coverage`; `AWAITING_APPROVAL` →
`state_awaiting_approval`; otherwise → `out_of_scope`. The shift window and role
come from the case's shift, formatted in the location's timezone, and the message
must still respect redaction (no health details, no internal ids).

### T3 — Tests
- An unclear message from an employee with an `OPEN` case re-asks the
  confirmation instead of redirecting.
- The same from the absent employee with an `OFFERING` case gets the coverage
  message, and with an `AWAITING_APPROVAL` case the approval message.
- A candidate with a pending offer gets the reminder.
- Terminal cases (`COVERED`, `ESCALATED`) still get the generic redirect, and an
  employee with nothing pending is unchanged — the existing tests stay green.

### T4 — Documentation
Spec §6.6's template table gains the new rows with their text, and this document
gets the evidence.

## Acceptance criteria

1. An employee whose absence is already registered never receives "I only handle
   absences and coverage" for an unclear message.
2. A candidate with an open offer is reminded of it.
3. The messages carry the real shift window and role, in the location's timezone.
4. `uv run pytest -q`, `uv run ruff check .`, `uv run mypy app` clean.

## Verification evidence

Observed on `feature/dashboard-live` (backend suite, ruff, mypy all run from `backend/`):

- RED (before implementation): the 4 new state tests failed against the old
  behavior — `out_of_scope` was sent instead of the state message, e.g.
  `test_unclear_message_from_candidate_with_pending_offer_reminds_it` failed
  with `assert 0 == 1` on `offer_reminder`. The 2 terminal-case tests passed
  from the start: they pin the pre-existing generic redirect.
- GREEN (after implementation): `uv run pytest -q` → **443 passed, 2 skipped**
  (was 437 passed, 2 skipped: +6 new tests, none changed, none removed).
  `uv run ruff check .` → **All checks passed!**. `uv run mypy app` →
  **Success: no issues found in 69 source files** (one intermediate error,
  a reused `shift` variable in `_send_state_aware_redirect`, fixed before the
  final run).
- Render check: `render('state_searching_coverage', employee_name='Iker',
  role='sala', start='15:00', end='23:00')` → "Vale Iker, tu ausencia del
  turno de sala de 15:00 a 23:00 ya está registrada y estoy buscando a
  alguien que te cubra. No tienes que hacer nada más." Note: the delegated
  check command passed `nombre=/rol=/inicio=/fin=` and fails with
  `KeyError: 'employee_name'` — the code convention is
  `employee_name/role/start/end` (consistent with every existing template),
  not the spec-table placeholder names.
- Priority order as implemented in `_send_state_aware_redirect`:
  1. most recent `PENDING` offer to the employee → `offer_reminder`
     (window of the offered shift);
  2. live case `OPEN` → `absence_confirm` (same wording, reads as a re-ask);
  3. live case `OFFERING` → `state_searching_coverage`;
  4. live case `AWAITING_APPROVAL` → `state_awaiting_approval`;
  5. otherwise (terminal cases and nothing pending) → `out_of_scope`,
     sent unchanged by the caller.
- Shift window/role come from the case's shift via
  `self._workforce.get_shift(shift_id)`, formatted with `_fmt` in the
  location's timezone; no health details, internal ids or case ids in any
  message body. New sends pass `conversation_id`/`employee_id` so the
  dashboard conversation shows them, like every other employee-facing send.
- Existing tests: **none had to change.** The three pre-existing
  `out_of_scope` assertions describe states with nothing pending (unclear
  shift choice with no case, bare "sí" with no case, second UNCLEAR from an
  employee with no case and no offers), so the generic redirect remains
  correct for all of them.
