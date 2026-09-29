# Feature: realtime-events (WebSocket `/ws/locations/{id}`)

**Status**: in progress
**Branch**: `feature/realtime-and-polish`
**Spec references**: §7.5 (`WS /ws/locations/{id}`), §7.6 (the dashboard updates itself)
**ADRs**: ADR-003 (single EC2, Caddy already routes `/ws/*`)

## Problem

The dashboard is pull-only. The reply to the manager's *own* action appears (the
Simulator polls after a send, actions invalidate queries), but a change produced
**elsewhere** — a candidate accepting, a case escalating, a rescue closed by the
worker — stays invisible until the manager refocuses the tab, acts, or reloads.
The user called this out ("no es tiempo real") and agreed to defer it; it is the
last thing that keeps the demo from feeling finished.

Spec §7.5 defines the endpoint for it, Caddy already forwards `/ws/*`, and the
frontend already has one place per screen that knows which queries to refetch,
so the work is bounded.

## Decisions (fixed, do not re-litigate)

1. **Events travel through Redis pub/sub**, the broker the project already runs
   for Celery. The worker is where the domain changes, and the API process is
   what holds the sockets; a Redis channel (`shift_rescue:events:<location_id>`)
   is the smallest correct bridge. No polling of the database, no second broker.
2. **The domain publishes one small, typed event per meaningful change**:
   `RESCUE_OPENED`, `OFFERS_SENT`, `OFFER_ACCEPTED`, `OFFER_DECLINED`, `CASE_COVERED`,
   `CASE_ESCALATED`, `CASE_CLOSED`, `MESSAGE_RECEIVED`, `MESSAGE_SENT`,
   `APPROVAL_REQUESTED`, `APPROVAL_DECIDED`. Each carries the rescue/shift ids and
   the location, and **never** a message body, a phone number, a name or any health
   detail.
3. **Publishing is best effort and never blocks a rescue**: a Redis failure logs
   and is swallowed, exactly like the runtime snapshot and the tracing bootstrap.
   The event bus is an injected port, so tests use a fake and the orchestrator
   keeps working when the broker is down (spec §9.3).
4. **The socket is authenticated**: the browser cannot set headers on a
   WebSocket, so the manager's JWT travels as a query parameter and is validated
   before the socket is accepted; an invalid or missing token closes with 4401
   without subscribing. Only the client's own location is streamed.
5. **The frontend refetches, it does not re-render from the payload.** One hook
   (`useLiveEvents`) maps each event type to the query keys it invalidates — the
   same keys the actions already invalidate — so the screens keep rendering from
   the API and nothing is duplicated in the client cache.

## Tasks

### T1 — Event bus (backend)
`app/events.py`: a typed `DashboardEvent` (name, location_id, rescue_id, shift_id,
origin, at) and an `EventBus` port with two implementations — a Redis publisher
(worker side) and a Redis subscriber/stream (API side) — plus a no-op fake for
tests. Publishing failures log and return.

### T2 — The domain publishes (backend)
`RescueOrchestrator` publishes at every transition listed above, from the single
places it already commits them (the state machine transitions, the wave send, the
idempotent inbound handler). A test proves each transition emits its event, and
that no payload contains a body, a phone, a name or a health flag.

### T3 — The endpoint (`app/api/ws.py`)
`WS /ws/locations/{location_id}?token=…`: validate the JWT (and the manager's
right to that location), accept, subscribe to the channel, forward events as
JSON, and clean up on disconnect. Unauthenticated or malformed → close 4401.
Redis unavailable → close with a clear code instead of hanging. Registered in
`app/main.py` (also in demo mode).

### T4 — The frontend hook (`services/liveEvents.ts` + screens)
`useLiveEvents(locationId)` opens the socket (reconnecting with backoff while the
tab is visible, closing on unmount), and invalidates the query keys that match the
event: rescues, shifts, approvals, conversations, the open rescue detail, metrics,
interpretations. A tiny visible indicator ("live" / "reconnecting") so the state is
honest, and no crash when the socket cannot open (the dashboard keeps working as
today).

### T5 — Tests and docs
- Backend: the event bus publishes/serializes correctly; each domain transition
  emits its event and respects the payload rules; the socket rejects an
  unauthenticated or malformed token, accepts a valid one and forwards a published
  event, and closes cleanly.
- Frontend: the hook connects with the token, invalidates the right keys per event
  type, reconnects with backoff and stops on unmount; screens render the indicator.
- `docs/runbook.md`: how to check the live channel; `docs/SHIFT_RESCUE_SPEC.md`
  §7.5 compliance note; evidence in this document.

### Parent verification (real stack, two browsers)

| Check | Result |
| --- | --- |
| Events reach Redis | `PSUBSCRIBE shift_rescue:events:*` saw `MESSAGE_RECEIVED` (origin `employee:emp_01_kitchen`) and `MESSAGE_SENT` (origin `agent`) |
| Payload privacy | the frame carries only `name`, `location_id`, `rescue_id`, `shift_id`, `origin`, `at` — no body, no phone, no name |
| Two-browser acceptance (criterion 1) | with the demo reset and one browser on **Today**, a rescue produced from a **second** browser moved the first one **2.5 s later without a reload** (the row gained `View detail` as the case opened) |
| Socket state indicator | no warning rendered, i.e. the channel was live |

### Two defects found while verifying (both fixed here)

1. **The worker never published.** `build_runtime` built the orchestrator without
   an event bus, so every transition went to the no-op: the channel was silent with
   the socket perfectly healthy. `app/runtime.py` now injects
   `RedisEventBus(settings.redis_url)`.
2. **The dev proxy did not forward `/ws`.** A WebSocket needs the upgrade
   forwarded (`ws: true`), so the handshake never completed and the dashboard sat
   on "Connecting to live updates…" forever. `frontend/vite.config.ts` proxies
   `/ws` now; `infra/Caddyfile` already routed it.
3. The first version of the endpoint deadlocked the suite: it awaited
   `websocket.receive()` while the client waited for the server, and cancelling a
   `receive()` blocked in the ASGI portal hangs the test client. The relay and the
   listener now run together and the socket is closed **before** anything is
   cancelled.

## Acceptance criteria

1. With two browsers open on the dashboard, accepting an offer from the Simulator
   moves the other one's Today board without a reload.
2. An unauthenticated socket is refused and never receives events.
3. Killing Redis makes the dashboard behave exactly as today (no crash, no hung
   socket) and the worker keeps processing messages.
4. No event payload carries a message body, phone, name or health detail.
5. Suites green: backend, frontend, ruff, mypy, oxlint, build, tsc.

## Verification evidence

_Pending._
