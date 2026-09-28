# Feature: demo-readiness

**Status**: in progress
**Branch**: `feature/dashboard-live`
**Spec references**: §7.5 (demo-only endpoints), §7.6 (screens)
**Design system**: `DESIGN.md` (§8 layout rules, colour tokens)

## Problem

Two things make the demo unusable or confusing, found by using it:

1. **The Simulator does not say who can report an absence.** The roster lists
   every employee with a shift *today*, including shifts that already ended
   (Ana García, 07:00–15:00, at 21:00) and employees with no shift at all
   (Ainhoa Tobal). Typing into those frames can only produce the "out of scope"
   reply, so the screen looks broken while the agent is behaving correctly.
   Verified: three of the three frames the user tried had nothing to report.
2. **The demo clock has no way back.** Advancing it is persisted in Redis and
   there is no reset, so a leftover offset (found at **+18 h 50 m** from testing)
   silently moves "now" for the whole worker: today's shifts read as already
   finished, the agent answers "out of scope", and stored timestamps jump into
   the future (a WhatsApp message stamped 22:51 appeared in the database as
   21:31 of a different day, which is what made a 40-minute "delay" look real).
   Nothing on screen says the clock is shifted.

Also requested by the user: **the Today screen should read as a modern dashboard
table** instead of the four-column board, keeping the existing colour tokens and
typography (their reference: a card with the green accent over cream,
"Cleaning · 08:00–12:00 / Covered by Xoel Barreiro").

## Decisions (fixed, do not re-litigate)

1. **The screen states what the agent will do.** Each phone frame shows the
   employee's situation relative to the current time — *on shift now*, *starts at
   18:00*, *shift ended at 15:00*, *no shift today* — and employees who can act now
   come first. Frames that cannot produce a rescue stay usable but say why.
2. **The demo clock is honest and reversible.** The header of the clock control
   shows the virtual time, the offset in human terms ("+2 h 30 m ahead") and a
   **Reset** action. A non-zero offset also renders a visible note on the screen,
   so nobody has to diagnose a database timestamp again.
3. **The reset is a real backend operation**, not a client trick: `POST
   /dev/clock/reset` sets the offset to zero and enqueues the reconcile sweep,
   and it is demo-gated exactly like the rest of `/dev`.
4. **Today becomes a table, not a new visual language.** One row per shift with
   role, window, assigned or absent employee, rescue state and the action, using
   the same tokens (`bg-surface`, `shadow-card`, `rounded-card`, the green accent
   over cream, serif headings). The four-state board disappears; the per-shift
   rescue detail is still one click away.
5. **No domain behaviour changes.** This is visibility and demo ergonomics; the
   orchestrator, the state machine and the API contract stay as they are.

## Tasks

### T1 — Roster clarity (`frontend/src/screens/SimulatorScreen.tsx`)
Per-frame situation computed from the shift window against the current time
(on shift now / starts at HH:MM / ended at HH:MM / no shift today), sorted so the
actionable ones come first, and a hint at the top when nobody can report an
absence *now* (with the suggestion to reseed or move the demo clock back).

### T2 — Demo clock reset (backend + frontend)
`POST /dev/clock/reset` (demo-gated, manager JWT, returns the new virtual time)
and the screen shows virtual time, offset and a Reset control; a non-zero offset
is explained in one line.

### T3 — Today as a table (`frontend/src/screens/TodayScreen.tsx`, `domain/today.ts`)
Replace the board with a modern dashboard table: one row per shift today, columns
for role, window, employee, status and rescue, with the rescue state as a badge
and the deadline as a compact countdown; responsive (cards below `md`, table from
`md` up, as the other wide screens already do). Keep `buildTodayColumns`'s
grouping logic where it is still useful for the badges, and keep the existing
tests meaningful by updating them to the new structure (their intent — who is
uncovered, searching, awaiting approval, covered — must still be asserted).

### T4 — Tests and docs
- Backend: `POST /dev/clock/reset` zeroes the offset, is demo-gated (404 outside
  demo envs) and requires a token.
- Frontend: the roster situation labels and the ordering; the reset control calls
  the endpoint; the Today table renders the same data the board did (uncovered /
  searching / awaiting approval / covered, and the countdown), both variants.
- `docs/runbook.md`: a short "Before a demo" checklist — reset the demo clock,
  make sure at least one employee is on shift now (reseed if the day is over),
  and what the frames' labels mean.
- Evidence in this document, including the browser verification.

## Acceptance criteria

1. Looking at the Simulator, it is obvious which employees can report an absence
   now and which cannot.
2. A leftover demo-clock offset can be undone from the UI in one click and is
   visible while it is set.
3. Today reads as a table with the same information the board carried.
4. No regression in the suites: `pnpm vitest run`, `pnpm build`, `pnpm lint`,
   `npx tsc --noEmit`, and the backend suite.

## Verification evidence

### T1 — Roster clarity

- `frontend/src/screens/SimulatorScreen.tsx`: `employeeSituation()` computes
  *On shift now / Starts at HH:MM / Ended at HH:MM / No shift today* against
  the demo clock's virtual "now"; frames sort on-shift first, then starting
  later, ended, no shift; a top banner appears when nobody can report an
  absence (suggests reseeding or resetting the clock). Frame layout, tokens
  and `VITE_USE_MOCK` behavior unchanged (mock roster has no shifts, so frames
  render with the honest "No shift today" label).
- Tests: labels, ordering (API order Ana/Bruno/Iker renders Iker first), the
  nobody-on-shift banner, and the offset note (`SimulatorScreen.test.tsx`).

### T2 — Reversible demo clock

- Backend `POST /dev/clock/reset` (`backend/app/api/dev_tools.py`): sets the
  Redis offset to `0`, enqueues `reconcile_stale_cases` (same as advance),
  returns the new virtual time + offset; demo-gated by the router-level
  `require_demo_environment` and manager-JWT-protected like its siblings.
- Frontend: `resetDemoClock()` in `services/api.ts`; `useDemoClock` now returns
  `offsetSeconds`/`virtualNow` and a `reset()` (mock mode resets to the
  documented 15:11). The clock control shows the virtual time, the offset in
  human terms (`formatDemoOffset`: "+6 h 30 m ahead" / "on real time"), a
  **Reset clock** button next to the advance presets, and — while the offset is
  non-zero — a one-line explanation that the agent's "now" is shifted. The
  broker-timers limitation line is kept verbatim.
- Tests: reset zeroes a leftover 67800 s offset, enqueues the sweep, 401
  without token, 404 in production (`test_dev_tools.py`); the screen tests
  call the endpoint and show the label transitions.

### T3 — Today as a table

- `frontend/src/domain/today.ts`: `buildTodayColumns` replaced by
  `buildTodayRows(shifts, rescues, approvals, roleOrder)` — one row per shift
  carrying the board's grouping intent as `state` (uncovered / searching /
  awaiting-approval / covered), the attached active rescue and its pending
  approvals, sorted uncovered -> searching -> awaiting -> covered, then role
  order then start time. Dead helpers removed: `groupShiftsByRole`,
  `minutesUntil`, `rescueCountdown`, `TodayColumns`. Kept: `formatShiftTime`,
  `formatCountdown`, `formatCountdownParts`.
- `frontend/src/screens/TodayScreen.tsx`: table (md+) with columns Role,
  Window, Employee ("Unassigned" when open, "(absent)" marker), Status, Rescue
  (badge + compact countdown + wave + approval kind) and Actions; cards below
  md; `overflow-x-auto`, `pointer-coarse:min-h-11` touch targets, existing
  tokens (`bg-surface`, `shadow-card`, `rounded-card`, green accent over cream,
  serif heading). The countdown itself opens the rescue detail (the old
  seeking-card affordance, kept so the App-shell navigation test still holds);
  rows with pending approvals keep the gold **Review approval** button.

### T4 — Suites and docs

- Backend: `437 passed, 2 skipped` (was 435+2; the two reset tests are new).
- Frontend: `152 passed` (was 148; net +4: situation labels/ordering/banner,
  offset note, reset endpoint, table rendering both variants, domain rows).
- `pnpm build`, `pnpm lint` (clean, no warnings), `npx tsc --noEmit -p
  tsconfig.app.json`, `uv run ruff check .` and `uv run mypy app` all pass.
- `docs/runbook.md`: "Before a demo (checklist)" added under the demo-simulator
  section: reset the clock, confirm an *On shift now* employee (reseed or reset
  when the day is over), walk one rescue end to end; the frame labels are
  explained inline.

### Browser verification at 360px

Not performed: this task ran headless (tests + build only, no browser
available). The responsive contract is covered structurally instead:
`today-cards` (`md:hidden`) and `today-table` (`hidden md:block
overflow-x-auto`) render as siblings and are both asserted in
`TodayScreen.test.tsx`; the 44px touch-target class is asserted on row action
buttons; the Simulator layout was not changed structurally. The 360px visual
pass for Simulator and Today remains for the parent's browser check.

### Follow-up — escalated rescues read as Escalated (parent-approved fix)

Defect found in the new table: a shift whose most recent rescue was ESCALATED
collapsed back into **"Uncovered — No candidates offered yet."** because
`buildTodayRows` only kept active statuses (`OFFERING`/`AWAITING_APPROVAL`) and
the ESCALATED case was dropped on the floor. Worse than the old board, which at
least made the rescue visible.

- `frontend/src/domain/today.ts`: `TodayRowState` gained `escalated`. Every case
  the data source delivers (active **or** terminal) is now kept, most recent per
  shift by `openedAt` (later array entry when dates are missing). State mapping:
  `OFFERING`→searching, `AWAITING_APPROVAL`→awaiting-approval (even on a staffed
  shift — the demo mock pairs a partial-coverage approval with a scheduled
  shift), `ESCALATED`→escalated unless the shift is staffed (`covered`/
  `scheduled` — the manager or the rota filled it afterwards; a covered shift
  never reads as escalated), `OPEN`→uncovered caption with the case still
  attached (nothing offered yet, but the detail is reachable), no case→uncovered
  only when absent/open.
- `frontend/src/screens/TodayScreen.tsx`: **Escalated** badge (solid
  `bg-error text-white`, the escalation colour used by the detail timeline) with
  the honest caption "The manager was notified — nobody covered it in time."; no
  stale 00:00 countdown. The Actions column already offered **View detail**
  whenever a case was attached, so terminal cases are now inspectable;
  **Review approval** stays for pending approvals.
- Tests: domain — escalated badge state, covered shift with an escalated case
  stays covered (case attached), most-recent-case selection, OPEN case keeps the
  detail reachable; screen — escalated row renders Escalated and never
  Uncovered, View detail opens the escalated rescue, covered-with-escalated
  reads Covered with the action. The screen tests inject data through a seeded
  QueryClient (`staleTime: Infinity`) because the hooks refetch the mock on
  mount.

Checks (all green):

1. `cd frontend && pnpm vitest run` → `Test Files 23 passed (23)`, `Tests 159 passed (159)`.
2. `cd frontend && pnpm build` → `✓ built in 137ms`; `pnpm lint` → exit 0;
   `npx tsc --noEmit -p tsconfig.app.json` → exit 0.
