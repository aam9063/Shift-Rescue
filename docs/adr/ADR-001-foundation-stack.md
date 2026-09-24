# ADR-001: Technology stack for the foundation

Status: accepted
Date: 2026-09-24
Deciders: FDE + product owner
Related: spec §7.2 (stack), Feature `foundation`

## Context

Shift Rescue needs a production-minded MVP: a WhatsApp-triggered rescue
orchestrator with a real-time manager dashboard, deterministic business rules,
an LLM confined to interpretation edges, and evaluation harnesses that gate CI.
The foundation must fix the stack so `domain-rules` and later features can run
in parallel.

## Decision

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.12 (pinned via uv) | Ecosystem standard for agents; uv gives fast, reproducible resolution. |
| API | FastAPI + Uvicorn | Async, Pydantic v2 typed contracts, native WebSockets for the dashboard. |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic | Fine-grained transaction control; `SELECT ... FOR UPDATE` needed for acceptance races. |
| Database | PostgreSQL 16 | Transactions, partial unique constraints (one ACCEPTED offer per rescue), jsonb for metrics/audit payloads. |
| Queues | Celery + Redis | Persistent workers for waves, timeouts and retries; Redis doubles as lock store and pub/sub for WebSocket fan-out. |
| Agents | Strands Agents SDK (pinned), **without the autonomous loop** | Model-provider abstraction, structured output, hooks, native OpenTelemetry. The state machine — not the LLM — orchestrates (see ADR on LLM/domain separation, coming with `llm-interpreter`). |
| Frontend | React 19 + TypeScript + Vite + Tailwind v4 + TanStack Query | Established in `frontend-foundation` / `manager-dashboard`. |
| Observability | structlog (JSON), OpenTelemetry → Langfuse (self-hosted), Sentry | One trace per rescue with cost/latency; alerts land in Ops screen and Sentry. |
| Tests | pytest + pytest-asyncio + Hypothesis (domain), Vitest + RTL (frontend) | Property tests for eligibility edge cases; hermetic unit runs, integration tests skip without `DATABASE_URL`. |
| Deploy | EC2 + Docker Compose + Caddy (TLS), images in ECR, secrets in SSM, GitHub Actions with OIDC | Cheapest persistent-worker setup for the demo; path to ECS Fargate/RDS/ElastiCache documented for production (ADR with `deploy-delivery`). |

## Consequences

- Single Python toolchain: `uv run pytest` is the only backend runner; CI mirrors it.
- The compose stack is the contract between backend and frontend for local
  development; `make up && make seed` must always leave a working API.
- Deferring Postgres schema separation (`workforce_mock`, `rescue`) to the
  `domain-rules` migration round keeps foundation migrations trivial; the ORM
  models carry the intent until then.
- Langfuse ships behind a compose profile until the `evals-observability`
  feature wires tracing exports.
