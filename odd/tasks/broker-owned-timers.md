# Feature: broker-owned-timers

**Status**: in progress
**Branch**: `feature/dashboard-live`
**Spec references**: §5.3 (waves, deadlines), §7.3 (schedulers), §9.1 (no rescue left stuck)
**ADRs**: ADR-002, ADR-003 (single EC2, Celery worker + beat)

## Problem

Timers never fire in the deployed stack, so no rescue ever escalates.

Verified live: two cases were past their deadline by 20 minutes and still sat in
`OPEN`/`OFFERING` with no escalation, and `/scheduler_ran_jobs` had **never**
appeared in the worker log since it started.

Root cause: the in-memory `SimScheduler` is a per-process object, and the worker
runs Celery's default prefork pool (12 children on this machine). The task that
opens a case registers the deadline timer in **its own** scheduler, while the
beat tick (`run_due_jobs`) lands in whichever child Celery picks — with its own
empty scheduler. They practically never coincide, so `run_due` always finds zero
due jobs. Restarting the worker also loses every pending timer (a limitation the
project had documented as accepted, which this change now removes).

Consequences: waves never advance, deadlines never escalate, approvals never
expire — the dashboard shows cards frozen at `00:00`, and the invariant "no
rescue is left stuck" is false in production.

## Goal

Timers are owned by the broker, survive a worker restart, and run on whichever
worker is free; and a case whose timer was lost (a crash between the database
commit and the enqueue) is recovered automatically instead of hanging forever.

## Decisions (fixed, do not re-litigate)

1. **One deferred Celery task per timer.** `schedule(run_at, name, payload)`
   becomes `apply_async(kwargs=…, countdown=max(0, run_at - now))`. Redis holds
   it and any worker executes it at the right time. The scheduler port stays the
   same, so the orchestrator and the eval harness do not change.
2. **`SimScheduler` stays for the eval harness** (fake clock, milliseconds) and
   for tests; production uses the broker-backed one. The backend is selected by
   `Settings.scheduler_backend` (`celery` default, `memory` for a single-process
   local run) and `build_runtime` accepts an injected scheduler, so tests and
   evals keep full control.
3. **Handlers are resolved in the executing process.** The deferred task looks
   the handler up in the runtime it builds itself — every worker process
   registers the same handlers at build time. An unknown name is a hard failure
   (a lost timer must be loud, not silent).
4. **A reconciliation sweep makes the system self-healing.** A beat task
   (every 60 s) finds cases whose deadline has passed and which still expect
   action, and re-enqueues their deadline job. This is what recovers cases whose
   timer was never enqueued, and it is also what unsticks the three existing
   cases in the demo database.
5. **Handlers stay idempotent.** The existing guards (status checks, the
   `OFFERS_QUEUED` audit marker) already make a double delivery harmless; the
   tests must prove it rather than assume it.

## Tasks

### T1 — `app/workers/celery_scheduler.py` (new)
`CeleryScheduler(clock, task=None)`: `register(name, handler)` (local registry of
the executing process), `schedule(run_at, name, payload) -> str` computing the
countdown from the injected clock and returning the broker task id, and
`pending_count()` / `run_due(now)` for port compatibility (the broker owns the
queue: document what they mean now). Add `handler_for(name)` to both schedulers
so nothing reaches into private attributes.

### T2 — Deferred-task entry point (`app/workers/tasks.py`)
`apply_scheduled_job(task_name, payload)`: builds the worker runtime, resolves
the handler, runs it through `run_async`, retries transient failures with bounded
backoff, and fails loudly (unknown name). Keep `process_inbound_message`,
`run_due_jobs` (still valid for the memory backend) and `purge_old_messages`.

### T3 — Reconciliation sweep (`app/workers/tasks.py`, beat)
`reconcile_stale_cases()`: for every case in `OPEN`/`OFFERING` whose
`deadline_at` has passed, enqueue its deadline job (idempotent by nature, since
`_on_deadline` re-checks the status). Register it in `beat_schedule` every 60
seconds. Log the count it recovered.

### T4 — Wiring (`app/runtime.py`, `app/core/config.py`)
`Settings.scheduler_backend`; `build_runtime(settings, *, scheduler=None)` picks
the backend unless one is injected. The worker gets the broker-backed scheduler;
the eval target keeps `SimScheduler`.

### T5 — Frontend: staffed shifts are visible (`frontend/src/domain/today.ts`)
Shifts in state `scheduled` (assigned, a normal day) currently fall into no
column, so "Covered today" reads 0 while nine shifts are staffed. Map them into
the covered column with a comment explaining the database vocabulary
(`scheduled` = staffed and untouched; `covered` = filled by a rescue).

### T6 — Tests and docs
- Countdown computation (future, already due → 0, clock respected).
- `apply_scheduled_job` dispatches to the registered handler and fails loudly on
  an unknown name.
- Firing a deadline or wave timeout **twice** does not duplicate offers and does
  not escalate an already-escalated case.
- `reconcile_stale_cases` re-enqueues only overdue cases that still expect
  action, and does nothing for covered/terminal ones.
- `build_runtime` uses the broker scheduler by default and honours an injected one.
- `today.test.ts`: `scheduled` shifts land in the covered column.
- `docs/runbook.md`: how timers work now, and the reconcile sweep as the first
  thing to check when a rescue looks stuck.
- Evidence in this document, including the live verification that the three
  overdue demo cases escalate.

### Parent live verification (real stack, real broker)

| Check | Result |
| --- | --- |
| A future timer is broker-owned | scheduled 40 s out; `celery inspect scheduled` showed `apply_scheduled_job` with `eta` 18:01:19 and `acknowledged: false` |
| Delivery at the right time | the worker executed `apply_scheduled_job[040ee78f]` at **18:01:19**, exactly the ETA, with no client-side queue |
| Overdue cases recovered | after the reconcile sweep: `case_ace1fd…` and `case_bc1809c0…` both **ESCALATED** (they had been frozen for over an hour) |
| Beat sweep is idempotent | the 60 s sweep re-enqueued the still-overdue OPEN case at 18:01:14 and the handler no-opped |
| Suite | 402 passed, 2 skipped; ruff and mypy clean; frontend 119 tests, build and lint clean |

### Second defect found by the first one (escalation was also broken)

Once the timers actually fired, the escalation **still** failed, and the worker log
showed why:

```
StringDataRightTruncationError: value too long for type character varying(64)
parameters: ('audit_case_bc1809c089fc4d0f9e0ae2b68141d083_escalated_1790359021_DEADLINE_REACHED', …)
```

`_escalate` composed an audit id of **81 characters** (`audit_<case>_escalated_<ts>_<event>`),
so the escalation transaction rolled back every single time and no rescue had ever
escalated in production. The quiet-hours marker had the same shape at exactly the
64-character limit, with no margin.

Both now use opaque `audit_<uuid>` ids (the reason lives in `payload` and the case
in `rescue_id`), and the existing width guard was extended to cover the escalation
and deferred-wave paths — it had only ever exercised the confirmation path, which
is exactly why it stayed green while production failed.

### Open gap found while verifying: a reported absence that is never confirmed

`case_93a8d259…` (Sonia Peral) is still **OPEN**: the employee reported the absence
and never answered the confirmation question. The state machine has no transition
for `OPEN + DEADLINE_REACHED` (only `CANDIDATES_COMPUTED` and
`NO_ELIGIBLE_CANDIDATES`), and the spec lists the `ghost` archetype ("no responde")
without defining what the system does about it. So the case waits forever, the
manager is never told, and the shift is left unattended.

This is a product decision, not a coding bug: either an unconfirmed absence
escalates to the manager after the deadline (recommended — someone must know), or
it needs an explicit expiry path. Requires a spec amendment in §5.4/§5.5, the
transition, the handler and an eval scenario for `ghost`.

## Acceptance criteria

1. A timer scheduled for the future is delivered by a worker at that time,
   whichever child is free.
2. Restarting the worker does not lose a pending timer.
3. The three overdue cases in the demo database escalate within a minute of the
   reconciler running.
4. Firing a handler twice changes nothing the second time.
5. Staffed shifts appear in the Today board.
6. `uv run pytest -q`, ruff, mypy, and the frontend suite/build/lint all clean.

## Verification evidence

Implemented 2026-10-03 (worker agent, branch `feature/dashboard-live`).

- **T1** `app/workers/celery_scheduler.py`: broker-owned `CeleryScheduler`;
  `schedule()` publishes one deferred `apply_scheduled_job` with
  `countdown = max(0, run_at - now)` and returns the broker task id;
  `pending_count()`/`run_due()` documented as port-compatibility no-ops (the
  broker owns the queue). `handler_for()` added to both schedulers.
- **T2** `apply_scheduled_job`: resolves the handler in the executing process,
  runs it via `run_async` (one-loop-per-process), retries transients with the
  same bounded backoff as `process_inbound_message`; unknown name → `KeyError`
  (permanent, loud). `process_inbound_message`, `run_due_jobs` and
  `purge_old_messages` untouched.
- **T3** `reconcile_stale_cases()`: enqueues `rescue_deadline` for every
  OPEN/OFFERING case past its deadline; beat entry `reconcile-stale-cases`
  every 60 s; logs `reconcile_stale_cases_recovered` when it recovers timers.
- **T4** `Settings.scheduler_backend` (`celery` default, documented `memory`);
  `build_runtime(settings, *, scheduler=None)` picks the backend unless one is
  injected. `app/evals/target.py` (SimScheduler, direct `RescueRuntime`) needs
  no change — verified by the untouched eval tests staying green.
- **T5** `today.ts`: `scheduled` shifts (staffed, untouched) now count in the
  covered column, with a vocabulary comment (`covered` = filled by a rescue).
- **T6** Tests: countdown (future/past/clock), dispatch + loud unknown name,
  transient retry, double delivery (wave timeout ×2 → no duplicate offers;
  deadline ×2 → one escalation, third delivery on a terminal case → no-op),
  reconcile sweep (only overdue non-terminal; repeat-safe), backend selection
  (celery default / memory / injected / unknown rejected), `today.test.ts`
  scheduled-in-covered.

Checks:

1. `cd backend && uv run pytest -q` → **402 passed, 2 skipped** (was 383+2;
   +19 new tests).
2. `cd backend && uv run ruff check .` → **All checks passed!**
3. `cd backend && uv run mypy app` → **Success: no issues found in 67 source
   files**.
4. `uv run python -c "...beat_schedule..."` →
   `['purge-old-messages', 'reconcile-stale-cases', 'run-due-jobs']`.
5. `cd frontend && pnpm vitest run` → **Test Files 17 passed (17), Tests 119
   passed (119)**.
6. `cd frontend && pnpm build` → **✓ built in 137ms**.
7. `cd frontend && pnpm lint` → oxlint, **exit 0**, no findings.

Assertion fix (parent-approved, option 1): the TodayScreen column-count test
asserted `getAllByText('2').length >= 2`, which the T5 fix made stale — with
`scheduled` shifts correctly counted, the covered column badge reads **6**
(2 `covered` + 4 `scheduled`) and the approvals badge keeps its own count. The
assertion now scopes to the covered column (`within` the "Covered today"
region) and expects exactly `6`; no other assertion changed and the test was
not weakened (no `toBeGreaterThan`). All 119 frontend tests pass.

Not verified here (needs the deployed stack): the live escalation of the three
overdue demo cases within a minute of the reconciler running (acceptance 3)
and delivery of a real future timer by a prefork child (acceptance 1). Both
follow from the same mechanics the unit tests exercise; confirm on the next
demo boot via `reconcile_stale_cases_recovered` in the worker log.
