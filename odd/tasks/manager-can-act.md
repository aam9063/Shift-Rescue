# Feature: manager-can-act

**Status**: in progress
**Branch**: `feature/dashboard-live`
**Spec references**: §5.3 (deadlines and escalation), §6.4 (actionable escalation summary), §7.5 (`POST /api/rescues/{id}/close`), §7.6 (screens)
**Design system**: `DESIGN.md`

## Problem

The user drove the product and could not use it. Five verified defects turn the
manager's flow into a dead end:

1. **The Simulator looks broken.** The agent's answer takes 10–15 s (worker + LLM)
   and nothing refreshes: you type, your own message appears, and the reply never
   shows until you reload by hand. Verified in a browser walkthrough: the send
   works (the message and the reply both reach the database), but the screen does
   not show the reply.
2. **The manager has nothing to do on an escalated case.** The detail screen for
   an escalated rescue renders the timeline, the candidates and *only* the
   navigation buttons. The backend has `POST /api/rescues/{id}/close` and
   `POST /api/approvals/{id}/approve|reject`; neither is reachable from the rescue
   detail. Spec §5.3 promises "escalated to the manager with an actionable
   summary" and §6.4 defines what that summary contains — neither is on screen.
3. **An escalated case reads as "Uncovered".** The Today screen only receives
   active cases, so an `ESCALATED` case disappears from the data and the row falls
   back to "Uncovered — No candidates offered yet": the exact opposite of what
   happened (candidates were offered and nobody accepted).
4. **A terminal case still shows a countdown** ("00:00 minutes left") although
   nothing is pending.
5. **Pending offers survive the escalation**, so the candidates of a dead case
   still read "pending" and the agent will keep reminding them (the state-aware
   reply fires on a case that no longer exists).

## Decisions (fixed, do not re-litigate)

1. **The screen must show the agent's answer without a reload.** After sending
   from a phone frame, the thread polls until the agent replies (bounded, with a
   visible "the agent is replying…" state and a stop condition), and the Today
   board and the open case refresh as soon as the reply lands.
2. **The manager acts from the rescue detail.** The detail gets the actions the
   spec already defines: **Close case** (`POST /api/rescues/{id}/close`, enqueued,
   202) and, for `AWAITING_APPROVAL`, approve/reject without leaving the screen.
   Terminal cases show no actions other than closing the loop visually.
3. **An escalated case explains itself and says what to do**: what the agent
   tried (who was contacted and what each answered, per §6.4), what options
   remain, and the honest instruction that the manager resolves it outside the
   system and then closes the case. No health details, ever.
4. **Today sees the day's cases, terminal included**, so a shift reads
   `Escalated` / `Covered` / `Searching` / `Uncovered` truthfully.
5. **Nothing pending keeps a countdown.** Countdowns render only for states with
   a live deadline.
6. **Escalation cancels the offers that are still open** (domain rule), so no
   candidate is left "pending" on a closed case and the agent stops chasing them.

## Tasks

### T1 — Simulator shows the reply (`frontend/src/screens/SimulatorScreen.tsx`, `services/dashboard.ts`)
After a successful send, poll that conversation's thread (e.g. every 3 s up to
~30 s, stopping as soon as a new outbound message appears) plus the Today board,
and show a small "the agent is replying…" line while waiting. Keep the send
button disabled while in flight to avoid duplicates.

### T2 — Manager actions in the detail (`frontend/src/screens/RescueDetailScreen.tsx`, `services/api.ts`, `hooks.ts`)
A primary **Close case** action (confirm dialog, 202 semantics, refresh after) and,
when the case is `AWAITING_APPROVAL`, the approve/reject actions inline. Report
the outcome honestly (the worker applies it). Touch targets and the responsive
contract apply as everywhere else.

### T3 — Escalated cases read truthfully (`frontend/src/domain/today.ts`, `TodayScreen.tsx`, `services/api.ts`)
Feed the board the day's cases including terminal ones; a shift whose latest case
is `ESCALATED` shows the Escalated badge and the §6.4-style explanation (who was
contacted, what the options are), never "Uncovered".

### T4 — No countdown on terminal states (`TodayScreen.tsx`, `RescueDetailScreen.tsx`)
Render the countdown only for live deadlines (`OPEN`, `OFFERING`,
`AWAITING_APPROVAL`); terminal cases show the outcome instead.

### T5 — Cancel open offers on escalation (`backend/app/services/orchestrator.py`)
When a case escalates, cancel the offers that are still `PENDING` (with the same
cancellation path used when a shift gets covered) so no candidate is left waiting
on a dead case. Tests: escalating a case with pending offers cancels them and
audits it; a covered case behaves as today.

### T6 — A demo script that matches reality (`docs/demo-script.md`)
Rewrite the walkthrough so someone can follow it without knowing the system:
what each screen is for, the exact steps to produce a rescue from the Simulator
(including that the agent's answer takes ~10 s), what happens at each state, and
what the manager does when a case escalates (resolve it, then close it in the
detail). Adjust `docs/runbook.md` if the flow described there drifts.

## Acceptance criteria

1. Sending from a phone frame shows the agent's reply within the polling window,
   with no manual reload.
2. An escalated case can be closed from the dashboard, and the state changes.
3. An escalated shift reads as Escalated on Today, with an actionable summary.
4. No countdown is rendered for a terminal case.
5. Escalating a case cancels its open offers.
6. Suites green: backend `uv run pytest -q`, frontend `pnpm vitest run`, plus
   ruff, mypy, build, lint, tsc.

## Verification evidence

_Completed on `feature/dashboard-live` (worker delegate, uncommitted)._

- T1: `useSendDemoMessage` polls the sent conversation's thread every 3 s up to
  ~30 s (10 attempts), stopping on the reply, on the bound, and on unmount;
  frames show "the agent is replying…", disable the send control in flight,
  and refresh the thread/roster/Today queries when the reply lands.
- T2: detail screen gained a confirmed **Close case** action (`POST
  /api/rescues/{id}/close`, 202 semantics, honest "applies in a moment" copy,
  query refresh) and inline **Approve/Reject** for `AWAITING_APPROVAL` via the
  existing `decideApproval` path. Terminal cases render no actions.
- T3: `getDayRescues` feeds `buildTodayRows` the day's cases, terminal
  included; the active-rescue counter keeps its own measure
  (`countActiveRescues`). Escalated rows show the §6.4 contacted summary.
- T4: countdowns only for `OPEN`/`OFFERING`/`AWAITING_APPROVAL`; terminal
  heroes/cells show the outcome (Escalated at HH:MM, Covered by <name>).
- T5: `_escalate` cancels still-pending offers through `_cancel_other_offers`
  (same path as the covered flow) and records the cancelled ids on the
  ESCALATED audit event.
- T6: `docs/demo-script.md` rewritten as a newcomer walkthrough; runbook
  "before a demo" step 3 now ends with the manager close.

Checks (all green):

1. `cd backend && uv run pytest -q` — 445 passed, 2 skipped
2. `cd backend && uv run ruff check .` — All checks passed!
3. `cd backend && uv run mypy app` — Success: no issues found in 69 source files
4. `cd frontend && pnpm vitest run` — 175 passed (23 files)
5. `cd frontend && pnpm build && pnpm lint && npx tsc --noEmit -p tsconfig.app.json` — built, oxlint clean, tsc clean

Behavioral note: the old late-acceptance test (a "sí" after escalation
creating an approval) was rewritten — per decision 6 the escalation cancels
the open offers, so a late acceptance now gets the polite redirect and no
approval. Covered-case behavior is unchanged (integration race tests green).
