# Feature: Degradation and hardening (`resilience`)

Status: **in progress**
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

- [ ] AC1: With `agent_paused` on, an inbound absence produces a manager
      forward + audit event, and **no** case, offer or LLM call.
- [ ] AC2: The outbound limiter blocks the (N+1)-th message in the window with
      an audit event and an alert, without breaking the flow.
- [ ] AC3: The purge task deletes message bodies older than the retention
      window and keeps audits/cases; idempotent and tested.
- [ ] AC4: A status surface reports `degraded` + reasons (breaker open, LLM
      unavailable, agent paused) and is unit-tested.
- [ ] AC5: Operations screen renders the degraded banner from the status hook.
- [ ] AC6: `llm_down_degraded` and `hris_failure_escalates` scenarios stay
      green; full suite green; lint + types clean.
- [ ] AC7: Work-unit commits recorded.

## Tasks

- [ ] T1 — Agent pause enforcement (TDD).
- [ ] T2 — Outbound per-employee rate limit (TDD).
- [ ] T3 — Retention purge task (TDD).
- [ ] T4 — Degraded status surface + dashboard banner (TDD).
- [ ] T5 — Full verification, docs (runbook/eval-report), close.

## Verification evidence

(appended per task)

## Commits

(appended per commit)

## Progress / Next step

Next: T1.
