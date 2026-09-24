# Shift Rescue — developer commands.
# Windows note: `make` is unavailable on plain Windows shells; either run the
# underlying commands directly (see each target) or use Docker/WSL.

COMPOSE = docker compose -f infra/docker-compose.yml

.PHONY: up down logs seed test test-backend test-frontend lint lint-backend lint-frontend dev-backend dev-frontend

## Boot the full local stack (postgres, redis, api, worker, beat)
up:
	$(COMPOSE) up -d --build

## Stop the stack and remove containers (volumes preserved)
down:
	$(COMPOSE) down

## Follow logs from all services
logs:
	$(COMPOSE) logs -f

## Run migrations and seed the demo data inside the running api container
seed:
	$(COMPOSE) exec api uv run python -m app.db.seed_cli

## Run every test suite
test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest

test-frontend:
	cd frontend && pnpm vitest run

## Run all linters and type checks
lint: lint-backend lint-frontend

lint-backend:
	cd backend && uv run ruff check app tests migrations && uv run mypy app

lint-frontend:
	cd frontend && pnpm lint

## Run the backend and frontend dev servers
dev-backend:
	cd backend && uv run uvicorn app.main:create_app --factory --reload --port 8000

dev-frontend:
	cd frontend && pnpm dev
