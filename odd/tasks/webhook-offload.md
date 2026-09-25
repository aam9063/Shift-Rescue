# Feature: webhook-offload

**Status**: in progress
**Branch**: `feature/webhook-offload` (from `feature/llm-runtime-wiring`)
**Spec references**: §7.4 (idempotent inbound), §7.5 (webhook < 200 ms, no LLM in it), §7.2 (Celery), §9.3 (degraded status)
**ADRs**: ADR-002, ADR-004 (open deviation: webhook awaits the interpretation)

## Problem

Wiring the LLM exposed a deviation from spec §7.5 that was invisible while the
webhook only ran the deterministic parser:

- The inbound Twilio webhook **awaits** `orchestrator.handle_inbound()`, so it
  now blocks on the interpretation call for 1–3 s instead of answering in under
  200 ms.
- The spec requires: validate the signature, persist the message with a unique
  `provider_message_id` (200 and stop when it already exists), **enqueue a
  task**, and never call the LLM inside the webhook.
- Orchestration currently lives in the **API process**, which is also why the
  wave timeouts are driven by an `asyncio` ticker in the FastAPI lifespan
  ("until Celery beat owns it"). Celery beat exists in both compose files but
  schedules nothing: `purge_old_messages` has no `beat_schedule` entry at all,
  so the retention purge never runs automatically.
- Moving the orchestrator into the worker breaks the in-process introspection
  used by `/api/status`: `llm_configured`, `circuit_open` and `agent_paused`
  currently read the API's own orchestrator, interpreter and circuit breaker.

## Goal

The inbound webhook answers immediately and the worker does the thinking, with
no behaviour loss: same idempotency, same degraded-mode reporting, timeouts
still firing, and the retention purge finally scheduled.

## Decisions (fixed, do not re-litigate)

1. **The Celery worker owns orchestration.** One shared runtime factory builds
   the orchestrator (with the interpreter from `build_interpreter()`) and the
   `SimScheduler` inside the worker process. The API process no longer builds
   either.
2. **Beat owns time.** A periodic task (`run_due_jobs`, every 5 s) drives
   `scheduler.run_due(...)` and publishes a small runtime snapshot to Redis;
   the same schedule finally wires the daily retention purge. The FastAPI
   lifespan ticker is removed.
3. **Enqueue failure is loud.** If the broker rejects the task, the webhook logs
   an error and returns **500** so Twilio retries — never a silent 200 that
   drops an employee's message.
4. **The status probe stops reaching into process internals.** Provider state
   comes from configuration (`is_provider_configured`), while circuit-breaker
   and paused state come from the snapshot the worker publishes; a missing
   snapshot means "no degradation observed" (closed breaker), matching today's
   semantics.
5. **Idempotency stays where it already works**: `handle_inbound` →
   `_persist_inbound` rejects a duplicate `provider_message_id` (spec §7.4).
   The task must not add a competing mechanism.
6. **Local demo keeps working with `docker compose up -d`**, which already
   starts `worker` and `beat`.

## Tasks

### T1 — Shared worker runtime (`app/runtime.py`, new)
`RescueRuntime` dataclass (session factory, channel, workforce adapter, clock,
scheduler, orchestrator, interpreter) plus `build_runtime(settings)` and a
memoized `get_worker_runtime()` for the worker process. It absorbs the
construction currently inlined in `get_twilio_service()`.

### T2 — Celery tasks (`app/workers/tasks.py`)
- `process_inbound_message(from_phone, message_sid, body)`: runs the async
  service through `asyncio.run`, with bounded retries
  (`max_retries=3`, exponential backoff, `acks_late` already on) for transient
  failures only. A duplicate `message_sid` must be harmless.
- `run_due_jobs()`: ticks the worker scheduler and publishes the runtime
  snapshot (`llm_configured`, `circuit_open`, `agent_paused`) to Redis with a
  TTL, so the API can report it.
- `purge_old_messages` stays, now actually scheduled.

### T3 — Celery beat (`app/workers/celery_app.py`)
`beat_schedule`: `run-due-jobs` every 5 s, `purge-old-messages` daily at 03:00
`Europe/Madrid`.

### T4 — Webhook slims down (`app/api/webhooks_twilio.py`)
- `/inbound`: validate → parse → enqueue → 200 TwiML. No orchestrator, no
  interpreter, no workforce adapter in the API process.
- Enqueue failure → 500 plus an error log naming the message sid.
- `/status`: keeps a DB-only `update_status` (no orchestrator needed).
- Split `TwilioInboundService` so the DB-only path does not require an
  orchestrator.

### T5 — Status probe (`app/api/status.py`, `app/agent/factory.py`)
- Add `is_provider_configured(settings) -> bool` to the factory (pure check:
  provider enabled **and** credential present; constructs nothing, calls no
  network).
- The probe reads that plus the Redis snapshot; no private attribute access
  into another process's objects.

### T6 — Lifespan (`app/main.py`)
Remove the scheduler ticker; keep `configure_tracing`/`shutdown_tracing` and log
one line stating that the worker owns scheduling.

### T7 — Tests and docs
- Webhook answers in under 200 ms and enqueues exactly once with the exact
  arguments (stub task).
- Enqueue failure returns 500 and logs.
- Duplicate `provider_message_id` processed once through the task path.
- Task retries on a transient failure and not on a permanent one.
- Beat schedule contains both entries with the expected intervals.
- Status probe: configured/unconfigured provider, snapshot present/absent.
- Runbook: worker/beat are required for the demo; what to check when a message
  gets no reply; `docs/adr/ADR-004` deviation marked closed; spec §7.5
  compliance note.

## Acceptance criteria

1. `POST /webhooks/twilio/inbound` returns 200 in well under 200 ms with the
   LLM configured, and the interpretation happens in the worker process.
2. A duplicate `MessageSid` results in exactly one orchestration run.
3. Wave timeouts still fire with only the worker and beat running (no API
   ticker).
4. `/api/status` still reports degraded reasons, now from configuration plus
   the published snapshot.
5. Broker down → 500 and an error log, never a silent drop.
6. `uv run pytest -q`, `uv run ruff check .`, `uv run mypy app` clean.

## Verification evidence

_Pending — recorded as each task closes._
