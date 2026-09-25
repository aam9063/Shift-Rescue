# Feature: Degradation and hardening (`resilience`)

Status: **closed**
Branch: `feature/resilience` (from `dev`)
Created: 2026-09-25

## Objective

Deliver spec Feature 7: degraded mode without the LLM, agent pause, fault
injection in the workforce adapter and the LLM client, outbound message
limits, and retention purge — with the dashboard reflecting the degraded
state. DoD: the "LLM down" and "HRIS failure" scenarios pass, and the
dashboard shows the degraded banner.

## What already exists (from earlier features)

| Piece | Where |
|---|---|
| LLM circuit breaker + deterministic parser fallback | `app/agent/llm.py`, `app/services/orchestrator.py` |
| Scenario `llm_down_degraded` (parser keeps working) | `evals/scenarios/` |
| HRIS assignment failures: retries ×3 → technical escalation | `orchestrator._finalize_assignment` |
| HRIS failure injection (`fail_next_assignments`) | `app/integrations/workforce/mock.py` |
| Scenario `hris_failure_escalates` | `evals/scenarios/` |
| `LocationSettings.agent_paused`, `ranking_weights`, quiet hours | `app/db/models.py` |
| Alert rules (stuck rescue, LLM error rate, low confidence, delivery, cost) | `app/observability/alerts.py` |

## Scope (what this feature adds)

- **Agent pause enforcement**: when `agent_paused` is true for a location, the
  orchestrator takes no agent action; inbound messages are forwarded to the
  manager and audited (spec §9.3).
- **Outbound limits**: at most N messages per employee per hour (configurable,
  default 3); excess sends are dropped, audited and alerted (§9.4).
- **Retention purge**: message bodies are purged after the configured
  retention window (default 30 days in the demo), leaving the audit trail
  intact; exposed as a task the scheduler/beat can run (§10).
- **Degraded state surface**: the orchestrator exposes whether it is running
  degraded (LLM breaker open / LLM not configured / agent paused) and the API
  reports it, so the dashboard can show the banner.
- **Dashboard**: the Operations screen shows the degraded banner when the
  status hook reports it (mock-backed until the dashboard API slice lands).

Out of scope: real HRIS integrations, Sentinel/Sentry paging, multi-region.

## Acceptance criteria

- [x] AC1: With `agent_paused` on, an inbound absence produces a manager
      forward + audit event, and **no** case, offer or LLM call.
- [x] AC2: The outbound limiter blocks the (N+1)-th message in the window with
      an audit event and an alert, without breaking the flow.
- [x] AC3: The purge task deletes message bodies older than the retention
      window and keeps audits/cases; idempotent and tested.
- [x] AC4: A status surface reports `degraded` + reasons (breaker open, LLM
      unavailable, agent paused) and is unit-tested.
- [x] AC5: Operations screen renders the degraded banner from the status hook.
- [x] AC6: `llm_down_degraded` and `hris_failure_escalates` scenarios stay
      green; full suite green; lint + types clean.
- [x] AC7: Work-unit commits recorded.

## Tasks

- [x] T1 — Agent pause enforcement (TDD).
- [x] T2 — Outbound per-employee rate limit (TDD).
- [x] T3 — Retention purge task (TDD).
- [x] T4 — Degraded status surface + dashboard banner (TDD).
- [x] T5 — Full verification, docs (runbook/eval-report), close.

## Verification evidence

- T1: RED -> GREEN 3 tests — paused agent forwards the message to the manager (health details redacted), writes `AGENT_PAUSED_FORWARD`, opens no case and sends no offers; unpaused flows unchanged. Migration `0004` makes `audit_event.rescue_id` nullable for case-less events. `47a6ca0`.
- T2: RED -> GREEN — `max_outbound_per_hour` (default 3) enforced at the single send choke point, counted per employee over a rolling hour; blocked sends write `OUTBOUND_LIMIT_EXCEEDED` + `OUTBOUND_LIMIT_ALERT` without breaking the flow; other employees unaffected. Offer messages now create their conversation rows, and outbound messages are stamped by the injected clock (deterministic). `0c0ff1e`.
- T3: RED -> GREEN 2 tests — `purge_old_messages` deletes messages older than the window (30 days default, `MESSAGE_RETENTION_DAYS`), keeps audits/cases, returns the count and is idempotent; Celery task `app.workers.tasks.purge_old_messages` + `python -m app.observability.retention` CLI. `df47b6f`.
- T4: RED -> GREEN 6 backend + 2 frontend tests — pure `degraded_reasons`/`build_status` (LLM not configured, circuit open, agent paused) exposed at `GET /api/status`; Operations screen renders the degraded banner from the status hook. `8354e88` + frontend commit.
- T5: full suite 225 backend (+2 integration skipped without DB), 83 frontend, 16 eval scenarios (including `llm_down_degraded` and `hris_failure_escalates`), ruff/mypy/oxlint clean, build clean.

## Commits

- `47a6ca0` feat(backend): enforce agent pause by forwarding inbound messages to the manager (TDD)
- `0c0ff1e` feat(backend): cap outbound messages per employee per hour with audit and alert (TDD)
- `df47b6f` feat(backend): retention purge task with Celery entry point and manual CLI (TDD)
- `8354e88` feat(api): degraded status endpoint with pure reason composition (TDD)
- frontend commit: degraded-mode banner on the Operations screen (TDD)

## Progress / Next step

Feature **resilience closed**. Spec features 0-7 are complete; only
`deploy-delivery` T3/T4 (instance + first deploy) remain, deferred by user
decision on cost with the resume plan in `odd/tasks/deploy-delivery.md`.

The runbook/eval-report live on `feature/deploy-delivery`; their resilience
sections (agent pause, outbound limits, purge, `GET /api/status`) are added
there so both documents stay together.

## Commits

(appended per commit)

## Progress / Next step

Next: T1.
