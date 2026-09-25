# Feature: Cimientos (`foundation`)

Status: **closed**
Branch: `feature/foundation`
Created: 2026-09-24

## Objective

Deliver spec Feature 0: working monorepo foundation for the backend —
`backend/` structure per spec §7.7, Docker Compose (api, worker, beat,
postgres, redis, langfuse), `make up` and `make seed` functional, CI with
lint and tests green, TDD runners configured (`uv run pytest`), and ADR-001
with the stack decisions.

## Problem / Why

The frontend foundation exists (see `manager-dashboard` feature, slices 1-4).
The backend needs the same base: a FastAPI service that boots, a reproducible
dev environment, database scaffolding with migrations, and CI — so that
`domain-rules` (Feature 1) can start on solid ground.

## Scope

In scope:
- `backend/` skeleton: FastAPI app factory, `/health` endpoint, pydantic-settings config, structlog JSON logging stub.
- Tooling: `uv` project pinned to Python 3.12, ruff, mypy (strict on `domain/`), pytest + pytest-asyncio, pre-commit config.
- DB layer scaffold: async SQLAlchemy engine/session, Alembic initialized, first migration with minimal `workforce_mock.location` and `rescue.manager` tables (expanded in `domain-rules`).
- `make seed` minimal: La Terraza del Puerto location + demo manager (full 25-employee seed arrives with `domain-rules`).
- Docker Compose: postgres, redis, api, worker, beat; langfuse behind a compose profile.
- Dockerfile for api/worker/beat (single image, different commands).
- Makefile: up, down, seed, test, lint, format, dev.
- GitHub Actions CI: backend (ruff, mypy, pytest) + frontend (lint, vitest, build) jobs.
- ADR-001 documenting the stack decisions (spec §7.2).

Out of scope (later features): domain entities/rules (`domain-rules`), rescue orchestration, LLM agents, Celery task logic beyond a ping task, WhatsApp channel, deployment to AWS (`deploy-delivery`).

## Constraints

- Python 3.12 pinned via uv (spec §7.2); dependencies resolved with `uv`.
- TDD: RED observed before implementing behavior (health endpoint, config, seed).
- Tests must run without Docker: unit tests hermetic; integration tests skip when `DATABASE_URL` is absent.
- Technical artifacts in English; Conventional Commits.

## Acceptance criteria (spec Feature 0 DoD)

- [x] AC1: `backend/` structure matches spec §7.7 (all packages present, even if minimal).
- [x] AC2: `uv run pytest` runs green locally (unit; integration skips without DB).
- [x] AC3: `docker compose up` boots postgres, redis, api, worker, beat; api `/health` responds.
- [x] AC4: `make seed` creates the demo location and manager in the running Postgres.
- [x] AC5: CI workflow (backend + frontend jobs) present and valid YAML.
- [x] AC6: ADR-001 written in `docs/adr/`.
- [x] AC7: Work-unit commits recorded in this document.

## Tasks

- [x] T1 — Tooling + app skeleton: pyproject, app factory, `/health` (TDD), config (TDD), ruff/mypy/pytest wiring.
- [x] T2 — DB scaffold: async engine/session, Alembic init, first migration, minimal seed (TDD on seed logic).
- [x] T3 — Docker: Dockerfile, docker-compose.yml (+ langfuse profile), Makefile targets verified.
- [x] T4 — CI + ADR-001 + README section for backend.
- [x] T5 — Full verification (`make test`, `make lint`, compose up smoke), close feature.

## Verification evidence

- T1: RED (2 suites failing on missing `app.*`) → GREEN 5/5 → commit.
- T2: seed RED (missing `app.db.seed`) → GREEN; Alembic async env reads settings; migration `0001_foundation`.
- T3: `docker compose up -d --build` verified on this machine: all 5 services healthy, `/health` returns 200 (compose smoke run twice — host port 5433 to avoid a local Postgres clash). `make seed` equivalent (`app.db.seed_cli`) ran inside the api container: migration applied + rows verified via psql.
- T4/T5: full verification — backend 9/9 pytest, ruff clean, mypy strict clean; frontend 82/82 vitest, oxlint clean, vite build clean. CI workflow (backend+frontend jobs) + ADR-001 + root README written.

## Commits

- `d9b137e` feat(backend): uv project pinned to Python 3.12 with FastAPI app factory, health endpoint and settings (TDD)
- `30dc4f5` feat(backend): async DB scaffold with Alembic migration, minimal idempotent demo seed and seed CLI
- `3ccc8b4` feat(infra): Dockerfile, docker-compose stack (postgres/redis/api/worker/beat + langfuse profile) and Makefile
- CI/ADR/README commit: (appended below after final docs commit)

## Progress / Next step

Feature **closed**. Spec Feature 0 DoD met: clone → `make up && make seed` → API responds; `odd/tasks/` exists; project registered in Engram. Next feature per spec order: `domain-rules` (Feature 1). Branch rebased onto updated `dev` (which includes the merged manager-dashboard UI).
