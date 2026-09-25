# Feature: demo-simulator

**Status**: in progress
**Branch**: `feature/dashboard-live`
**Spec references**: §7.5 (`POST /dev/simulator/{employee_id}/messages`, `POST /dev/clock/advance`), §7.6 (Demo simulator screen), §9.3
**ADRs**: ADR-004 (runtime wiring)

## Problem

The full rescue flow can only be driven from real WhatsApp phones: the dashboard
can *watch* the agent work, but it cannot *produce* the work. Demoing the core
value (an employee reports an absence, candidates get offers, someone accepts,
the shift is covered, the deadline escalates) needs either a second phone or ten
minutes of waiting for a wave timeout.

The spec already defines the answer — two demo-only endpoints — and the
frontend already ships a **Demo simulator** screen rendering phone frames with
mock conversations. The endpoints were never implemented, so the screen still
shows mock data.

## Goal

A reviewer can reproduce the whole story from the dashboard in under a minute,
with no second phone and no waiting, while every message travels the *same*
domain path a real WhatsApp message travels.

## Decisions (fixed, do not re-litigate)

1. **The simulator injects into the real pipeline, never around it.** The
   endpoint resolves the employee and enqueues the same Celery task the Twilio
   webhook enqueues (`process_inbound_message`), with a synthetic
   `provider_message_id`. Idempotency, dedup, conversation threading, LLM
   interpretation, auditing and delivery all behave exactly as in production, and
   the simulated message lands in the employee's real conversation.
2. **Demo-only, and gated twice.** The routes exist only when the app runs as
   `local`, `test` or `demo` (`APP_ENV`), and they still require a manager JWT.
   A production deployment must return 404 for them.
3. **The clock offset is shared, not local.** `POST /dev/clock/advance` moves a
   Redis-backed offset that the worker's clock reads, so every process agrees on
   "now" (deadlines, quiet hours, eligibility windows). Immediately after moving
   it, the reconcile sweep is enqueued so cases that have become overdue escalate
   without waiting for the 60 s beat tick.
4. **Honest limitation, documented:** broker timers keep their real-time ETA, so
   advancing the demo clock does not fast-forward a wave timeout. What the demo
   needs — deadlines, escalations and every employee reply — is covered by the
   sweep and by simulating the replies; the UI must say so.
5. **The Simulator screen keeps its visual language** (phone frames, design
   tokens, English copy) and gains: the real employee list, their real
   conversations, a "send as this employee" action, and the demo clock.

## Tasks

### T1 — Demo clock (`app/core/clock.py`, `app/core/config.py`)
`DemoClock(offset_source)` returning `now + offset`, with the offset read from
Redis under one key; `Settings.demo_clock_enabled` (true for local/test/demo).
`build_runtime` uses it in demo mode and keeps `SystemClock` otherwise. Redis
being unavailable must degrade to the system clock with one warning, never break
the worker.

### T2 — Dev endpoints (`app/api/dev_tools.py`, new)
- `POST /dev/simulator/{employee_id}/messages` `{text}`: 404 for an unknown
  employee, 202 after enqueueing the inbound task with a synthetic sid.
- `POST /dev/clock/advance` `{seconds}`: moves the offset and enqueues the
  reconcile sweep; returns the new virtual time.
- `GET /dev/clock`: the current virtual time and the offset (the UI shows it).
- `GET /api/employees?location_id=`: the employee list the screen needs
  (id, display name, role, today's shift window, whether a conversation exists
  and its id). This extends the spec's table for the demo screen and is
  documented as such.
- All of them: manager JWT required; 404 when the environment is not a demo one.

### T3 — Frontend: the Simulator screen reads and writes real data
Wire `SimulatorScreen.tsx` to `GET /api/employees`, `GET /api/conversations/{id}/messages`
and the dev endpoints: pick an employee, see their real thread, send a message as
them, and advance the demo clock with a visible button and the current virtual
time. Keep the phone-frame layout and the design tokens; English copy; the mock
stays for `VITE_USE_MOCK`. The screen must explain, in one short line, that
timers follow real time.

### T4 — Tests and docs
- Endpoint tests: unknown employee → 404; non-demo `APP_ENV` → 404; missing or
  manager-less token → 401; valid call → 202 and the task enqueued with the
  expected arguments (stubbed enqueue); clock advance returns the new offset and
  enqueues the sweep; Redis failure degrades gracefully.
- `DemoClock` behaviour: offset applied, zero offset equals the system clock,
  Redis error falls back.
- Frontend: the screen renders the real employee list, sends a message and
  advances the clock (mocked fetch), and still renders the mock behind
  `VITE_USE_MOCK`.
- `docs/runbook.md`: how to demo without a second phone, the `APP_ENV` gate, and
  the real-time-timer limitation.
- Evidence in this document.

## Acceptance criteria

1. With the stack running, a message sent from the Simulator screen opens a real
   rescue in the Today board and threads into that employee's conversation.
2. Advancing the demo clock escalates an overdue case within seconds.
3. The routes answer 404 when `APP_ENV=production`.
4. Every simulated message is indistinguishable, in the database, from a real
   one except for its synthetic provider id.
5. `uv run pytest -q`, ruff, mypy, and the frontend suite/build/lint all clean.

## Verification evidence

_Completed 2026-09-25 on `feature/dashboard-live` (T1-T4 implemented by the
worker subagent; commits and review are the parent's decision)._

- **T1 demo clock**: `DemoClock(offset_source)` in `app/core/clock.py` reads
  the offset from one documented Redis key
  (`shift_rescue:demo_clock_offset_seconds`) through an injectable source;
  missing key / unparseable value / Redis error -> offset 0 + one warning per
  reason per clock, never an exception. `Settings.demo_clock_enabled` (local/
  test/demo) gates it; `build_runtime` wires `DemoClock` in demo environments
  and `SystemClock` otherwise (`RescueRuntime.clock` widened to `Clock`).
- **T2 dev endpoints**: `app/api/dev_tools.py` (simulator messages -> the
  same `process_inbound_message` task the webhook enqueues, `sim_<uuid>` sid,
  202; clock advance with ±30-day bound -> Redis `INCRBY` + reconcile sweep
  enqueue; `GET /dev/clock`) and `app/api/employees.py`
  (`GET /api/employees?location_id=` with today's shift + conversation id).
  Double gate: `create_app` registers the `/dev` router only when
  `demo_clock_enabled`, and `require_demo_environment` (in
  `app/api/dependencies.py`) answers a hard 404 otherwise; manager JWT
  required on every route.
- **T3 screen**: `SimulatorScreen.tsx` reads the real roster and threads,
  sends through the endpoint and advances the shared clock; API methods live
  in `services/api.ts`, hooks in `services/dashboard.ts`, type in
  `domain/types.ts`; mock mode (`VITE_USE_MOCK`) preserved.
- **T4 tests/docs**: `tests/unit/test_clock.py` (+10), `test_runtime.py` (+2),
  `tests/unit/api/test_dev_tools.py` (13), `tests/unit/api/test_employees.py`
  (4); `SimulatorScreen.test.tsx` (5). Runbook "Demo without a second phone"
  subsection added.

Checks (exact outputs):

1. `cd backend && uv run pytest -q` -> `428 passed, 2 skipped, 2 warnings in
   45.87s`
2. `cd backend && uv run ruff check .` -> `All checks passed!`
3. `cd backend && uv run mypy app` -> `Success: no issues found in 69 source
   files`
4. openapi probe (local) -> `['/api/employees',
   '/dev/simulator/{employee_id}/messages', '/dev/clock/advance',
   '/dev/clock']`; with `APP_ENV=production` -> `['/api/employees']` (no
   `/dev/` route advertised or served)
5. `cd frontend && pnpm vitest run` -> `Test Files 18 passed (18) / Tests 124
   passed (124)`; `pnpm build` -> `built in 157ms`; `pnpm lint` (oxlint) ->
   exit 0; `npx tsc --noEmit -p tsconfig.app.json` -> clean.

Production-gate proof: the OpenAPI probe above with `APP_ENV=production`,
plus `test_dev_routes_are_not_advertised_or_served_in_production` (routes
absent from the schema and `GET /dev/clock` -> 404) and
`test_dev_routes_answer_404_when_settings_change_after_startup` (dependency
404 even with the router registered).

Known limitation (documented, not fixed by design): broker timers keep their
real-time ETA, so advancing the demo clock does not fast-forward a wave
timeout. Not verified end-to-end against a live Redis/worker stack (tests are
hermetic); acceptance 1-2 need a manual demo run.
