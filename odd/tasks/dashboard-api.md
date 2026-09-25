# Feature: dashboard-api

**Status**: in progress
**Branch**: `feature/dashboard-live`
**Spec references**: §7.5 (REST API table, JWT for managers), §7.6 (screens), §9.2 (metrics), §10 (redaction)
**ADRs**: ADR-003 (deployment), ADR-004 (provider)

## Problem

The dashboard is a complete UI with **no HTTP client**: every screen renders
mock data from `frontend/src/services/dashboardMock.ts` and
`frontend/src/services/mock.ts`. The backend exposes only `/health`,
`/api/status` and the Twilio webhooks. The spec's §7.5 endpoint table was never
implemented, so nothing the agent does is visible in the product.

The frontend already has the seam: `DashboardDataSource` (interface),
`MockDashboardDataSource` (implementation) and the hooks in
`frontend/src/services/hooks.ts` and `frontend/src/services/dashboard.ts`.
Swapping the implementation is what connects the product end to end.

## Decisions (fixed, do not re-litigate)

1. **Real login, spec §7.5.** `POST /api/auth/login` issues a JWT (HS256,
   `JWT_SECRET`, 12 h). Every `/api` route except login requires a bearer token.
   `GET /api/interpretations*` additionally requires role `operator` (spec
   §7.5). `/health`, `/api/status` and the Twilio webhooks stay public
   (liveness, degraded banner, provider-signature validation).
2. **Real password hashing.** The seed writes an Argon2 hash of a documented
   demo password for both seeded managers; the placeholder
   `"demo-not-a-real-hash"` must never authenticate anything. Invalid, expired
   or missing tokens answer 401; wrong role answers 403.
3. **The dashboard reads through the same domain, never around it.** Approval
   decisions are applied by the worker (the orchestrator owns that logic), so
   `POST /api/approvals/{id}/approve|reject` enqueues a Celery task and answers
   202. Simple reads and the settings PATCH are queried directly.
4. **The response shapes are the frontend contract.**
   `frontend/src/domain/types.ts` is the source of truth for field names
   (camelCase JSON, ISO-8601 timestamps with offset). No renamed fields, no
   snake_case leaking into the API.
5. **Redaction holds** (spec §10): message bodies served to the dashboard are
   the stored redacted bodies; health details never appear in any response.
6. **Deferred, explicitly:** `/ws` real-time events, `/api/evals/runs*`, the
   `/dev/*` simulators and `POST /api/shifts/{id}/absence` (the WhatsApp flow
   already opens rescues; a manager-driven absence is its own unit).

## Tasks

### T1 — Auth (`app/api/auth.py`, `app/security/`)
`POST /api/auth/login` → `{access_token, token_type, expires_in, manager:{id, name, email, role, locationIds}}`.
Argon2 verification, JWT issue/verify, and FastAPI dependencies `current_manager`
and `require_role("operator")`. Settings: token TTL, CORS origins. Login failure
answers 401 with a generic message and never reveals whether the email exists.

### T2 — Seeds and settings
`SEED_*` demo credentials (documented in the runbook and shown on the login
screen), Argon2 hashes at seed time, `cors_origins` and `jwt_expires_minutes`
in `Settings`.

### T3 — Read endpoints (spec §7.5, dashboard slice)
`GET /api/locations`; `GET /api/locations/{id}/shifts?from&to`;
`GET /api/locations/{id}/settings`; `GET /api/rescues?status&location_id`;
`GET /api/rescues/{id}` (timeline from `audit_event`, offers with candidate
names, exclusion reasons, metrics);
`GET /api/approvals?status&location_id`;
`GET /api/conversations?location_id&employee_id&has_rescue&from&to`;
`GET /api/conversations/{id}/messages` (redacted bodies + the interpretation of
each inbound message); `GET /api/interpretations?...` (filters per spec, role
`operator`); `GET /api/interpretations/{id}`;
`GET /api/metrics?location_id&from&to` (LLM cost per day, p50/p95 interpreter
latency, low-confidence rate, delivery failures, stuck rescues).

### T4 — Write endpoints
`POST /api/approvals/{id}/approve|reject` (enqueue a Celery task, 202);
`PATCH /api/locations/{id}/settings` (agent pause and ranking weights);
`POST /api/rescues/{id}/close`.

### T5 — CORS
Allow only the configured origins, with `Authorization` in the allowed headers.

### T6 — Tests and docs
- Auth: valid login; unknown email; wrong password; the legacy placeholder hash
  never authenticates; missing/expired/tampered token → 401; `manager` role on
  an operator route → 403.
- Endpoints: each returns the frontend contract shape (assert exact field
  names) against a seeded temp-file SQLite database; health details never appear
  in any response; approval enqueue failure → 500; pagination/filter parameters
  behave.
- `docs/runbook.md`: demo credentials, how to call an endpoint with a token,
  CORS origins.
- `odd/tasks/dashboard-api.md`: evidence.

## Acceptance criteria

1. `POST /api/auth/login` with the seeded demo credentials returns a working
   token; any `/api` route without it answers 401.
2. Every response body matches `frontend/src/domain/types.ts` field for field.
3. Approval decisions are applied through the worker, never inline in the API.
4. No health detail and no unredacted body is returned anywhere.
5. CORS accepts the dashboard origin and rejects others.
6. `uv run pytest -q`, `uv run ruff check .`, `uv run mypy app` clean.

## Verification evidence

_Completed on `feature/dashboard-live` (worker delegation, T1–T6)._

- **T1 Auth**: `app/security/passwords.py` (Argon2id via `argon2-cffi`, fail-closed; the
  legacy placeholder `demo-not-a-real-hash` never verifies), `app/security/tokens.py`
  (HS256 via `pyjwt`, TTL from settings), `app/api/auth.py` (`POST /api/auth/login`,
  generic 401 on any failure), `app/api/dependencies.py` (`current_manager` → 401,
  `require_role("operator")` → 403). Response is camelCase per the parent decision:
  `{accessToken, tokenType, expiresIn, manager:{id, name, email, role, locationIds}}`.
- **T2 Settings/seed**: `jwt_expires_minutes` (720) and `cors_origins`
  (`http://localhost:5173`) in `Settings`; `seed.py` writes Argon2 hashes of the
  documented `DEMO_PASSWORD` for both managers and refreshes them on reseed (the
  placeholder can never survive); managers now get `location_ids`.
- **T3 Reads**: `/api/locations`, `/api/locations/{id}/shifts?from&to`,
  `/api/locations/{id}/settings`, `/api/rescues?status&location_id`,
  `/api/rescues/{id}` (timeline from `audit_event`, offers with candidate names,
  exclusion reasons only when stored on `rescue_case.metrics.candidates`, previews),
  `/api/approvals?status&location_id`, `/api/conversations?...`,
  `/api/conversations/{id}/messages` (redacted bodies + inbound interpretation
  summaries), `/api/interpretations*` (role `operator`; validation = OK above the
  confidence threshold, else `retry`; trace link only when a trace id is stored —
  currently none is, so `traceUrl` is null), `/api/metrics?location_id&from&to`
  (cost/day, p50/p95, low-confidence rate, delivery failures, stuck rescues).
- **T4 Writes**: approve/reject/close validate then enqueue
  `apply_approval_decision` / `close_rescue_task` and answer 202; enqueue failure →
  500 with an error log. `PATCH /api/locations/{id}/settings` (incl. `agentPaused`)
  writes directly. The orchestrator gained `close_rescue` (ESCALATED →
  MANAGER_RESOLVED; OFFERING/AWAITING_APPROVAL cancel like an approved cancel_rescue;
  OPEN/terminal states are a no-op — no invented transitions).
- **T5 CORS**: `CORSMiddleware` with exactly `settings.cors_origin_list`,
  `Authorization` + `Content-Type` headers, GET/POST/PATCH/OPTIONS.
- **T6 Tests/docs**: `tests/conftest.py` (seeded temp-file SQLite world),
  `test_auth.py` (21 tests), `test_dashboard_endpoints.py` (17),
  `test_dashboard_contract.py` (11, exact field-name sets from
  `frontend/src/domain/types.ts` / `dashboardMock.ts` — a rename breaks them),
  runbook §0 (credentials, curl with token, CORS).

Checks (all green, final run):

1. `uv run pytest -q` → `375 passed, 2 skipped` (was 317 + 2).
2. `uv run ruff check .` → `All checks passed!`
3. `uv run mypy app` → `Success: no issues found in 65 source files`.
4. `uv run python -c "from app.api.auth import router; print([r.path for r in router.routes])"`
   → `['/api/auth/login']`.
5. Route check on `create_app()`: FastAPI 0.141 wraps included routers in
   `_IncludedRouter` (no `.path`), so the literal `{r.path for r in ...}` command
   raises `AttributeError` — pre-existing version behavior, unrelated to this change.
   Via `create_app().openapi()['paths']` all routes are present: `/api/auth/login`,
   `/api/locations`, `/api/locations/{location_id}/shifts`,
   `/api/locations/{location_id}/settings`, `/api/rescues`, `/api/rescues/{rescue_id}`,
   `/api/rescues/{rescue_id}/close`, `/api/approvals`,
   `/api/approvals/{approval_id}/approve`, `/api/approvals/{approval_id}/reject`,
   `/api/conversations`, `/api/conversations/{conversation_id}/messages`,
   `/api/interpretations`, `/api/interpretations/{interpretation_id}`, `/api/metrics`,
   `/api/status`, `/health`, `/webhooks/twilio/*`.

Deviations/limits:

- Login response keys are camelCase (`accessToken`, …) per the parent's task text,
  which supersedes the older snake_case mention in this document.
- `waveTotal` comes from `rescue_case.metrics["wave_total"]` (the orchestrator does
  not persist it today); `interpretedByAi` only when an audit payload carries it.
- Langfuse trace links require a stored `trace_id`; none is persisted yet, so the
  detail returns `traceUrl: null` (nothing invented).
- Health details/unredacted bodies: asserted per response in the endpoint tests.
