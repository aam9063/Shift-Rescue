# Feature: polish-round (notices, seed anchors, absence endpoint, small cleanups)

**Status**: closed
**Branch**: `feature/realtime-and-polish`
**Spec references**: §7.5 (`POST /api/shifts/{id}/absence`), §6.4 (escalation summary), §9.2 (snapshot), §9.3 (degradation), §10 (retention)
**Related**: `odd/tasks/realtime-events.md` (the WebSocket, first unit of the same round)

## Why

Four gaps were left after the dashboard, evaluation and demo work landed. None of
them was a defect in the spec's terms, and all of them were visible to whoever
used the product:

1. **Notices reached a phone and left no trace.** The manager's escalation and
   coverage notices go to a phone (not to an employee conversation), so nothing
   was persisted and the rescue timeline showed a case that escalated "by
   itself". The race loser's "already covered" reply was an employee message and
   was not stored either, so their thread looked unanswered.
2. **A demo day could be dry.** The seeded rotation has fixed windows, so a demo
   late in the evening had nothing in progress and nothing starting "today": the
   Simulator offered no frame able to report an absence.
3. **Two endpoints of §7.5 were missing**, and the dashboard's "Report absence"
   button was dead: the manager could not mark an absence from the product at
   all.
4. **Three loose ends**: a beat entry that ticked an obsolete in-memory
   scheduler, a declared-but-unused `SENTRY_DSN`, and a Langfuse link that was
   always null because the trace id was never stored.

## What was done

| Unit | Change |
| --- | --- |
| Notices | One helper sends and audits every manager notice on the case (`MANAGER_NOTIFIED` with the template, or `MANAGER_NOTIFY_SKIPPED` with the reason when the manager has no reachable phone — the attempt is recorded, never a delivery claim). The race loser's reply now carries the conversation. Both audit types render in the timeline ("Manager notified" / "Manager could not be reached"). |
| Seed | When the seeded day is dry the seed anchors two shifts to the current hour — one in progress, one starting soon — assigned to employees the rotation left free that day, and only for the window that is actually missing. Nothing changes during working hours, and the pool comes from the rotation itself so an anchor never schedules somebody who does not exist. |
| Absence endpoint | `POST /api/shifts/{id}/absence` enqueues a task (202) that opens the rescue through the confirmed-absence path, auditing `ABSENCE_MARKED` with the manager as the actor and guarding against a second case on redelivery. 404 for an unknown or out-of-location shift, 409 when it is already absent or already has a live case. |
| The button | The floating "Report absence" action opens a dialog listing today's still-scheduled shifts and marks the chosen one absent, with honest 202 copy and the server's refusal surfaced. |
| Cleanups | `run-due-jobs` (obsolete in-memory tick) is gone from beat and the runtime snapshot it published moved to `reconcile-stale-cases`, which is the heartbeat the degraded banner depends on. Sentry initializes when the DSN is set, best effort and silent when unset. The OTel trace id is stored on each interpretation so the decision detail can link to its Langfuse trace. |

## Evidence

| Check | Result |
| --- | --- |
| Backend suite (Windows) | **515 passed**, 2 skipped; ruff and mypy clean |
| Backend suite (Linux CI image) | **515 passed**, 2 skipped, 0 failures |
| Frontend suite | **199 passed**; build, oxlint and tsc clean |
| Notices, live | an escalation recorded `MANAGER_NOTIFIED {template: manager_escalated}` on the case |
| Seed, live | after a reseed: **5 shifts in progress and 2 starting within six hours** |
| Absence action, live (browser) | the button opened the dialog with **10 shifts**; marking one was accepted and Today showed that shift **absent with its rescue searching** |
| Live channel (from `realtime-events`) | two browsers: a rescue produced in one moved the other's board **2.5 s later with no reload** |

### Deliberately not done

The EC2 deployment (T3/T4 of `deploy-delivery`) stays deferred by user decision:
the repo artifacts are complete and the runbook has the exact commands, to be run
when the user decides.
