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

### Parent live verification (real stack, real keys)

`docker compose -f infra/docker-compose.yml up -d --build api worker beat`, then
three signed webhook requests from a script (Twilio HMAC signature computed from
the real auth token, employee `emp_09_floor` mapped to a real phone):

| Observation | Result |
| --- | --- |
| `POST /webhooks/twilio/inbound` latency | **50.3 ms** (cold), **15.0 ms** and **19.8 ms** (warm) — budget is 200 ms |
| Worker handling (off the request path) | `worker_inbound_processed ... recognized=True`, ~2.9 s per message |
| Concurrency | two worker children processed two messages in parallel without event-loop or pool errors |
| Beat | `run_due_jobs` ticked every 5 s (`succeeded in 0.0033s`) |
| API process | logs `scheduling_owned_by_worker`; no orchestrator, no ticker |
| Langfuse after the tracing fix | 4 observations exported from the worker for one message: `invoke_agent Strands Agents` (SPAN), `chat` (GENERATION), `execute_event_loop_cycle` (SPAN), `Interpretation` (TOOL) |
| Final suite | `296 passed, 2 skipped`, ruff clean, mypy clean (53 files) |

Acceptance criteria 1, 2, 3, 5 and 6 verified live or by test. Criterion 4
(`/api/status` from configuration plus the published snapshot) is covered by
unit tests with fakes; it was not exercised against a live Redis snapshot in
this pass.

### Follow-up found while verifying (not fixed here)

The `interpretation` table is never written by any service: `grep` over
`app/` shows the SQLAlchemy model at `app/db/models.py:165` and no writer, and
a live run recorded 0 rows while the LLM answered correctly. The "Agent
decisions" screen therefore has no real data source yet (it renders mock data).
This predates the offload and needs its own work unit: persist each
interpretation (intent, confidence, model, prompt version, cost, latency,
validation result) with a link to its Langfuse trace.

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

Recorded 2026-09-25 on `feature/webhook-offload` (worker offload T1–T7):

- `cd backend && uv run pytest -q` → `290 passed, 2 skipped in 21.12s`
  (2 skips are the PostgreSQL integration tests without `DATABASE_URL`).
- `cd backend && uv run ruff check .` → `All checks passed!`
- `cd backend && uv run mypy app` → `Success: no issues found in 52 source files`
- `cd backend && uv run python -c "from app.workers.celery_app import
  celery_app; print(sorted(celery_app.conf.beat_schedule or {}))"` →
  `['purge-old-messages', 'run-due-jobs']` — both entries present.
- `cd backend && uv run python -c "from app.api.webhooks_twilio import router;
  print([r.path for r in router.routes])"` →
  `['/webhooks/twilio/inbound', '/webhooks/twilio/status']` — both routes kept.
- Measured inbound webhook latency (TestClient, signature validated, enqueue
  stubbed, 10 calls after warm-up): 1.2–1.7 ms per request, max **1.7 ms** —
  well under the 200 ms budget of spec §7.5. The worker-side latency (LLM call,
  1–3 s) is off the request path by construction: the task body runs through
  `asyncio.run(get_worker_runtime().handle_inbound(...))`.
- Not verified live here (parent owns the terminal): a real WhatsApp message
  through `docker compose up -d` with worker + beat running, and Redis
  snapshot round-trip against a live broker — unit tests cover both via fakes
  and the parent will verify live afterwards.

### Regression found in live verification (2026-09-25)

The live run confirmed the offload itself: the webhook answered in 50 ms / 15 ms
(budget 200 ms), two messages were processed concurrently by two preforked
worker children with no event-loop errors, and beat ticked `run_due_jobs` every
5 s. It also exposed a defect invisible to the unit suite: **real
interpretation calls produced no Langfuse traces** (0 observations in the 15
minutes after two real messages), because `configure_tracing()` ran only in the
FastAPI lifespan and the worker never installed a `TracerProvider`.

Fix: `app/workers/tracing_bootstrap.py` connects to Celery's
`worker_process_init` (a provider inherited across a fork is not usable — its
`BatchSpanProcessor` exporter thread and locks do not survive `fork` — so every
child installs its own) and `worker_process_shutdown` (flush buffered spans
before exit; a lost batch is lost data). Imported from `celery_app.py` so any
worker loads it; tolerant by design (tracing disabled is a no-op, failures are
logged and swallowed so tracing never stops a worker boot). Covered by tests in
`test_celery.py` (init configures with current settings, disabled is a no-op,
failures swallowed) and `test_observability.py` (shutdown flushes, safe when
never configured, failures swallowed).
