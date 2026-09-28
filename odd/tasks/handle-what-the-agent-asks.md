# Feature: handle-what-the-agent-asks

**Status**: in progress
**Branch**: `feature/dashboard-live`
**Spec references**: §5.4 (absence confirmation), §5.5 (ambiguity: never guess), §6.2 (interpreter), §9.1 (nothing stuck)
**ADRs**: ADR-002 (prompt versioning), ADR-004

## Problem

Three defects of one family, all found by driving the product end to end: **the
agent asks something and the answer is not handled**.

1. **"Which shift?" is a dead end.** When an employee has two or more shifts in
   the 48-hour window — the common case on a real schedule — `_handle_absence_report`
   sends `ask_which_shift` and returns. Nothing consumes the reply: there is no
   state, no prompt branch and no resolution, so the employee answers and the
   absence is never reported. Verified live: Tomás Ibarra (`emp_19_bar`, shift
   in progress) reported an absence and nothing happened, because he also has a
   shift tomorrow. In the demo database only two employees have exactly one
   upcoming shift, and both already have cases: **the demo cannot open a new
   rescue at all.**
2. **The interpreter never receives the shift list.** The golden fixture sends
   `shifts_48h` and the prompt renders it, but the orchestrator does not send it,
   so the model cannot resolve which shift the employee means even when it is
   told. Third instance of the same fixture/production mismatch (after the
   withdrawal marker and the pending confirmation).
3. **An absence that is never confirmed hangs forever.** An employee who reports
   an absence and never answers the confirmation leaves the case in `OPEN`
   indefinitely: the state machine has no `OPEN + DEADLINE_REACHED` transition,
   so the manager is never told and the shift is left unattended in silence. The
   spec lists the `ghost` archetype ("no responde") without defining the
   behaviour. **Product decision taken: it escalates to the manager.**

## Decisions (fixed, do not re-litigate)

1. **Every question the agent asks has an answer path.** `ask_which_shift` is
   answerable: the orchestrator remembers it asked (using the persisted outbound
   message, the mechanism `_clarify_once` already uses) and resolves the reply.
2. **Resolution is the model's job first, the parser's second.** The interpreter
   receives the candidate shifts with their ids and returns `shift_reference`;
   the deterministic parser keeps working in degraded mode by matching "hoy",
   "mañana", a time or a role against the same candidates. Never guess: if the
   reply does not identify exactly one shift, ask once more and then redirect.
3. **The context the fixtures describe is the context production sends.** The
   orchestrator sends `shifts_48h` (with ids) and `pending_shift_choice` when it
   asked, and a contract test pins the key set so the eval fixture can never
   again measure a context the product does not produce.
4. **An unconfirmed absence escalates to the manager** when the deadline passes
   (the user's decision). The manager must know either way; the absence is not
   silently assumed.
5. **Prompt changes are new versions** (ADR-002): `interpreter_v5` adds the
   shift-choice branch; the version flows to every stored interpretation.

## Tasks

### T1 — Context the interpreter needs (`app/services/orchestrator.py`)
Send `shifts_48h` as `["<shift_id> <role> <HH:MM>-<HH:MM>", …]` for the
employee's upcoming shifts, and `pending_shift_choice` with the same candidates
when the last outbound message in the conversation was `ask_which_shift`.

### T2 — Resolve the answer (`app/services/orchestrator.py`)
On `ABSENCE_REPORT` carrying a `shift_reference` that matches one of the pending
candidates, open the case for that shift (same flow as the unambiguous path). If
the reply resolves to exactly one candidate deterministically, use it even in
degraded mode. If it resolves to nothing, send the question again at most once,
then the polite redirect.

### T3 — Prompt v5 (`app/agent/prompts/interpreter_v5.md`)
Add the branch: with `[pending_shift_choice=…]`, an answer that identifies one of
the candidates is `ABSENCE_REPORT` with that `shift_reference`; ambiguity stays
`UNCLEAR`; a plain "sí" here is not an offer acceptance. Bump `PROMPT_VERSION`.

### T4 — Ghost escalation (`app/domain/state_machine.py`, `app/services/orchestrator.py`)
`(State.OPEN, StateMachineEvent.DEADLINE_REACHED) → (State.ESCALATED, (SideEffect.NOTIFY_MANAGER,))`,
`_on_deadline` accepts an `OPEN` case, and the manager notification follows the
existing escalation path. Amend the spec §5.4/§5.5 with the rule (the project's
rule is that a behaviour change updates the spec) and record it in
`docs/assumptions.md` if it needs an assumption.

### T5 — Fixtures, scenarios and tests
- Golden: add rows for the shift-choice reply (context with `pending_shift_choice`),
  and keep every expected label byte-identical for existing rows.
- New eval scenario for the ghost: report → no answer → deadline → escalated and
  the manager notified.
- Context contract test: the exact key set the orchestrator sends, including
  `shifts_48h` and `pending_shift_choice` (this is the test that would have
  caught all three fixture/production mismatches).
- Orchestrator tests: two upcoming shifts → asks; a resolvable reply → case
  opened for the right shift; an unresolvable reply → asked once more then
  redirected; OPEN + deadline → ESCALATED with a manager notice.
- `docs/eval-report.md` and this document: evidence.

## Acceptance criteria

1. An employee with two upcoming shifts can report an absence by answering the
   question, and the case opens for the shift they named.
2. An unconfirmed absence escalates to the manager when the deadline passes.
3. The context the orchestrator sends contains every key the prompt branches on.
4. The demo can open a new rescue from the simulator with an employee who has
   two upcoming shifts.
5. `uv run pytest -q`, ruff, mypy clean.

## Verification evidence

Implemented on `feature/dashboard-live` (worker delegation; T1–T5 plus the
parent-approved refinements below).

- **T1 Context (dated):** `_shift_choices` sends
  `"<shift_id> <role> <YYYY-MM-DD> <HH:MM>-<HH:MM>"` (location-local start
  date; the end time stays HH:MM, so a night shift crossing midnight reads
  `19:00-03:00`) and the same list backs `shifts_48h` and
  `pending_shift_choice`. Without a date the model cannot map "el de hoy" onto
  a candidate — the hole the first format left. The orchestrator also sends
  `[today=YYYY-MM-DD]` (location-local) whenever the shift list is present:
  dated candidates alone still cannot say which date "hoy" is, and the prompt
  builder already renders extra string keys generically.
- **T2 Resolution:** unchanged in behaviour; the deterministic degraded path
  keeps resolving from the shift objects ("hoy"/"mañana" via the location tz,
  start time, role) — it never parses the candidate format. Covered by
  `test_degraded_mode_resolves_shift_choice_by_day` and the unresolvable
  ask-once-then-redirect test.
- **T3 Prompt:** `interpreter_v5` edited **in place** (format description,
  `[today]` anchor, examples mapped onto the dated list: "el de hoy" and
  "el de mañana" resolve against `[today]`; ambiguity and a bare "sí" stay
  UNCLEAR). Reasoning recorded per the parent's decision: v5 was created in
  this same uncommitted change and never shipped, so editing it keeps the
  version honest — ADR-002's rule is about attributability of shipped prompts,
  and inflating versions for an unreleased prompt would not improve it.
- **T4 Ghost escalation:** `(OPEN, DEADLINE_REACHED) → ESCALATED` with the
  manager notice; INV6 relaxed for the no-offers escalated case (RESCUE_OPENED
  was never emitted) but still pins `ABSENCE_REPORTED` + `ESCALATED`, so the
  ghost trail stays complete.
- **T5 Fixtures/tests:** golden `golden_151..154` updated to the dated context
  + `today` anchor; `golden_154` ("el de hoy") now expects ABSENCE_REPORT with
  `shift_reference: "shift_a"`; `golden_155` ("sí") kept byte-identical by
  decision (a bare "sí" answers nothing in the shift-choice state). The
  context-contract test pins the exact key set including `today` and the exact
  dated candidate strings. New scenario `ghost_unconfirmed_escalates`.

Golden rows touched (only rows added by this change): `golden_151`, `golden_152`,
`golden_153` (context format + anchor; labels unchanged), `golden_154`
(UNCLEAR → ABSENCE_REPORT + `shift_reference`, now resolvable against the dated
list), `golden_155` (untouched, byte-identical, by decision).

Checks (all green, final run):

1. `cd backend && uv run pytest -q` → **435 passed, 2 skipped, 2 warnings in
   48.40s**.
2. `cd backend && uv run ruff check .` → **All checks passed!**
3. `cd backend && uv run mypy app` → **Success: no issues found in 69 source
   files**.
4. `cd backend && uv run pytest -q tests/unit/evals` → **27 passed in 5.99s**
   (15 scenarios incl. `ghost_unconfirmed_escalates`, 0 invariant violations).

Not verified here: a live interpreter run against the new golden rows
(`uv run python evals/runner.py --provider interpreter` needs the real API key
and is the parent's measurement to take); the unit suite cannot exercise the
model, only the deterministic path and the context contract.
