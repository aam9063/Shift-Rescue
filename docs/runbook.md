# Runbook — Shift Rescue demo

Everything a maintainer needs to deploy, smoke-test, debug and roll back the
demo environment (single EC2 instance + Langfuse Cloud, see ADR-003).

## 0. Dashboard API access (demo credentials and CORS)

### Demo credentials

The seed (`backend/app/db/seed.py`) creates two dashboard users for the demo
location `loc_la_terraza` ("La Terraza del Puerto"). Both share one documented
demo password, `DEMO_PASSWORD` — a **seeded demo-system password, never a real
credential**:

| User | Email | Role | Password |
|---|---|---|---|
| Demo Manager | `manager@laterraza.demo` | `manager` | `laterraza-demo-2026` |
| Demo Operator | `operator@laterraza.demo` | `operator` | `laterraza-demo-2026` |

Passwords are stored as Argon2id hashes; a reseed always refreshes them, so
the legacy placeholder `demo-not-a-real-hash` can never authenticate.

### Login and calling the API

Every `/api` route except `POST /api/auth/login` requires a bearer token
(`GET /health`, `GET /api/status` and the Twilio webhooks stay public).
`GET /api/interpretations*` additionally requires the `operator` role.

```bash
# 1. Login (12-hour token, JWT_EXPIRES_MINUTES).
TOKEN=$(curl -fsS https://<domain>/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"manager@laterraza.demo","password":"laterraza-demo-2026"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')

# 2. Call any dashboard endpoint with the token.
curl -fsS https://<domain>/api/locations -H "Authorization: Bearer $TOKEN"
curl -fsS "https://<domain>/api/rescues?status=OFFERING&location_id=loc_la_terraza" \
  -H "Authorization: Bearer $TOKEN"
curl -fsS https://<domain>/api/locations/loc_la_terraza/settings \
  -H "Authorization: Bearer $TOKEN"

# 3. Writes answer 202: the decision/close runs in the Celery worker.
curl -fsS -X POST https://<domain>/api/approvals/<id>/approve \
  -H "Authorization: Bearer $TOKEN"
```

Failed logins are always a generic `401 {"detail":"Invalid email or password"}`
— the API never reveals whether the email exists. Missing, expired or tampered
tokens answer `401`; the wrong role answers `403`.

### Using the dashboard (SPA)

The dashboard asks for the same demo credentials on its login screen
(`manager@laterraza.demo` / `laterraza-demo-2026`, or the operator account for
the Agent-decisions screen, which requires the `operator` role). The session
(token + manager profile) lives in the browser's `localStorage`; any 401 from
an API call clears it and returns the user to the login screen.

Two Vite env vars (see `frontend/.env.example`) control how the SPA reaches
the API:

| Variable | Meaning |
|---|---|
| `VITE_API_BASE_URL` | API base URL. Empty (default) = same origin: the Vite dev proxy (`/api` → `http://localhost:8000`) and the deployed Caddy setup both serve the API from the web origin, so no CORS is needed. |
| `VITE_USE_MOCK` | Set to `true` to run the dashboard fully offline on mock data (offline demo mode; the test suite forces this). Any other value uses the live API. |

**Approvals are enqueued, not applied inline:** approve/reject answers `202`
and the Celery worker applies the decision. The dashboard invalidates its
queries after the POST, so the new state appears on the next refetch — typically
a second or two after the click, once the worker has run. If it never appears,
check the worker container (§4).

### CORS origins

The API allows **exactly** the origins in `CORS_ORIGINS` (comma-separated;
default `http://localhost:5173`), with `Authorization` and `Content-Type` as
allowed headers and `GET/POST/PATCH/OPTIONS` methods. Any other origin is
rejected by the browser. On EC2 set it to the demo domain, e.g.
`CORS_ORIGINS=https://<domain>` in SSM/deploy secrets.

## 1. What runs where

| Piece | Where |
|---|---|
| Dashboard (SPA) | EC2 container `caddy`, served from `/srv`, TLS by Let's Encrypt |
| API + Twilio webhooks | EC2 container `api` (proxied by Caddy at `/api`, `/webhooks`) |
| Celery worker + beat | EC2 containers `worker`, `beat` |
| PostgreSQL + Redis | EC2 containers, EBS-backed volume |
| LLM | OpenAI API (default), Anthropic or Bedrock by configuration (ADR-004) |
| Traces | **Langfuse Cloud** over OTLP/HTTP (ADR-003/A4) |
| Images | ECR (`shift-rescue-api`, `shift-rescue-web`) |
| Secrets | SSM Parameter Store under `/shift-rescue/prod/*` |

## 2. Configuration: LLM provider and Langfuse

The API reads **every** setting through `app/core/config.py`; nothing reads the
environment directly any more. Both integrations are optional by design: a
missing key degrades (deterministic parser, no traces) instead of failing.

### 2.1 LLM provider (OpenAI by default)

Set in `backend/.env` (locally) or in SSM `/shift-rescue/prod/*` (on EC2):

```bash
LLM_PROVIDER=openai                 # openai | anthropic | bedrock | none
OPENAI_API_KEY=sk-...               # required for openai
# OPENAI_BASE_URL=https://...       # any OpenAI-compatible gateway (NaN, proxies)
LLM_MODEL_INTERPRETER=              # empty = provider default (gpt-4o-mini)
LLM_TIMEOUT_SECONDS=10
LLM_CONFIDENCE_THRESHOLD=0.75
```

Verify at boot: the **worker** logs exactly one line
`llm_path provider=openai model=gpt-4o-mini` (secret-free) — the worker process
owns the orchestrator and the interpreter (the API only enqueues tasks). When
the provider is disabled or a credential is missing it logs `llm_disabled
reason=...` and keeps answering with the deterministic parser — **that warning
is the signal**, not an error. `LLM_PROVIDER=none` is the explicit kill switch
for the LLM path.

### 2.2 Langfuse Cloud (traces)

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com   # or https://cloud.eu.langfuse.com
# OTEL_EXPORTER_OTLP_ENDPOINT=            # overrides the derived Langfuse URL
```

The derived endpoint is `<LANGFUSE_HOST>/api/public/otel/v1/traces` with Basic
auth built from the two keys. Boot logs `tracing_enabled endpoint_host=...`, or
`tracing_disabled` when the keys are absent. Traces appear in Langfuse under
`service.name=shift-rescue-backend` and the environment from `APP_ENV`; the
provider's own model spans are included, so no extra instrumentation is needed.

Verify the keys without deploying:

```bash
cd backend && uv run python -c "
from app.core.config import Settings
s = Settings()
print('tracing:', s.tracing_enabled, s.traces_endpoint)
"
```

If traces never arrive, check in this order: the `tracing_enabled` line exists;
the endpoint host is the region that owns the keys (EU keys do not authenticate
against the US host); the keys are of the same project; the process actually
served traffic (spans are exported in batches).

## 3. Deploy

```bash
# From GitHub: Actions → "Deploy demo" → Run workflow (manual by design).
```

The workflow is **manual**: the demo instance is provisioned on demand to keep
the cost under control. It runs a preflight that fails with a clear message if
any of the four repository secrets is missing
(`AWS_DEPLOY_ROLE_ARN`, `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`). Once the
instance exists and the secrets are set, add `push: branches: [main]` back to
the trigger to get continuous delivery.

The workflow builds both images, pushes them to ECR, copies
`infra/docker-compose.prod.yml`, `infra/Caddyfile` and
`infra/deploy/remote-deploy.sh` to `/opt/shift-rescue`, and runs the remote
deploy script (secrets → `.env`, pull, migrate + seed, `up -d`, health check).

First time on a fresh instance:

```bash
scp -i <key.pem> infra/deploy/bootstrap-ec2.sh ubuntu@<host>:/tmp/
ssh -i <key.pem> ubuntu@<host> 'sudo bash /tmp/bootstrap-ec2.sh'
```

## 4. Smoke test

```bash
curl -fsS https://<domain>/api/../health        # {"status":"ok"...}
curl -fsS -o /dev/null -w '%{http_code}\n' https://<domain>/   # 200 (SPA)
# Twilio: send "hola" from a joined phone; the API answers instantly (200,
#   log `twilio_inbound_received`), and the worker then logs
#   `worker_inbound_processed ... recognized=true`
```

The **worker and beat containers are required for the demo**: the API only
enqueues the inbound task (spec §7.5), the worker runs the orchestration and
the LLM, and beat ticks the scheduler (`run-due-jobs`, every 5 s) plus the
daily retention purge. `docker compose ps` must show `api`, `worker`, `beat`,
`redis` and `postgres` up.

If a message gets no reply, check in this order:

1. `logs api | grep twilio_inbound_received` — did the webhook arrive and pass
   signature validation? A `500` line (`twilio_inbound_enqueue_failed`) means
   the broker rejected the task: check `redis` is up (Twilio retries on 500).
2. `logs worker | grep worker_inbound_processed` — did the worker pick it up?
   If not, the worker is down or stuck: `docker compose logs worker`.
3. `recognized=false` means the sender phone is not a seeded employee.
4. `logs worker | grep llm_disabled` — the agent may be answering as the
   deterministic parser (see §2.1).

### Demo without a second phone

The **Demo simulator** screen drives the real pipeline from the dashboard, so
the whole rescue story can be reproduced in under a minute with no second
WhatsApp phone:

1. Log in as the demo manager and open **Simulator**. The phone frames show
   the real employees (`GET /api/employees?location_id=`) with their real
   conversation threads.
2. Type as any employee and send: the API enqueues the *same* Celery task the
   Twilio webhook enqueues (`POST /dev/simulator/<employee_id>/messages`), so
   interpretation, threading, auditing and delivery behave exactly as with a
   real message. The message lands in the employee's real conversation and
   the Today board opens a rescue when the text reports an absence.
3. Use the demo clock to skip waiting: `+10 min` / `+1h` call
   `POST /dev/clock/advance`, which moves a Redis-backed offset shared by the
   API and the worker (`DemoClock`) and immediately enqueues the reconcile
   sweep, so overdue cases escalate in seconds.

**Gate:** these routes only exist when the app runs as a demo environment
(`APP_ENV=local`, `test` or `demo`; see `Settings.demo_clock_enabled`). In
production the router is not even registered — `GET /dev/clock` answers 404 —
and every route still requires a manager JWT.

**Known limitation:** broker timers (wave timeouts, offer expirations) keep
their real-time ETA — advancing the demo clock does not fast-forward a wave
timeout. Deadlines, escalations and employee replies are what the demo needs,
and those do follow the demo clock; the Simulator screen says so in one line.

### Check responsiveness

Open DevTools device toolbar and walk the four widths; nothing should scroll
horizontally at any of them:

- **360px (phone):** every screen reachable from the header hamburger drawer;
  the two wide tables render as stacked cards; no horizontal scrollbar; pills
  and drawer items feel comfortably tappable (44px minimum).
- **768px (tablet):** the drawer is gone and the main nav is inline; Settings
  and Evals show two columns; the tables render as tables.
- **1024px (desktop):** the operator nav appears; Evals and Ops show their full
  multi-column layout.
- **1440px:** content caps at 1440px wide with the extra cream margin.

## 5. Common operations

| Task | Command (on the instance, in `/opt/shift-rescue`) |
|---|---|
| Logs (all / one service) | `docker compose -f docker-compose.prod.yml logs -f [api]` |
| Recreate after config change | `docker compose -f docker-compose.prod.yml up -d` |
| Re-seed demo data | `docker compose -f docker-compose.prod.yml run --rm api uv run --no-dev python -m app.db.seed_cli` |
| Migrations | `docker compose -f docker-compose.prod.yml run --rm api uv run --no-dev python -m alembic upgrade head` |
| Update a secret | `aws ssm put-parameter --name /shift-rescue/prod/X --value '...' --type SecureString --overwrite` then re-run the deploy workflow |
| Pause the agent | Settings screen (or `PATCH /api/locations/<id>/settings`) |
| Rotate the SSH key | create a new key pair, add the public key to `~/.ssh/authorized_keys`, update the `EC2_SSH_KEY` secret |

### Timers (broker-owned, survive restarts)

Timers (wave timeouts, rescue deadlines, approval expirations) are owned by
the Redis broker, not by worker memory: scheduling a timer publishes one
deferred Celery task (`apply_scheduled_job`) whose countdown is computed
against the clock, and whichever worker child is free executes it when the
countdown expires. Restarting the worker therefore never loses a pending
timer. (The old per-process in-memory scheduler is the documented root cause
of the "no timer ever fired" incident: each prefork child had its own queue.)

Safety nets, in order:

1. Handlers re-check state before acting (`_on_deadline` only escalates an
   `OFFERING` case, `_on_wave_timeout` checks the `OFFERS_QUEUED` audit
   marker), so a redelivered timer changes nothing.
2. Beat runs `reconcile_stale_cases` every 60 s: any case still in
   `OPEN`/`OFFERING` whose `deadline_at` has passed gets its deadline job
   re-enqueued (log line `reconcile_stale_cases_recovered count=N`). This
   recovers a timer lost to a crash between the database commit and the
   enqueue.

Beat still ticks `run-due-jobs` (5 s), which drives the `memory` scheduler
backend (`SCHEDULER_BACKEND=memory`, for a single-process local run) and
refreshes the API status snapshot. `SCHEDULER_BACKEND=celery` is the
production default.

## 6. Incident playbook

| Symptom | First checks | Fix |
|---|---|---|
| 502 from Caddy | `logs caddy`, `logs api` | api container unhealthy → check `.env` (DATABASE_URL) and `logs api` |
| Dashboard blank | `logs caddy` (404 on assets?) | rebuild the web image (`frontend/Dockerfile.prod`) and redeploy |
| Twilio webhook returns 403 | `TWILIO_AUTH_TOKEN` mismatch, or the request did not come through Caddy | re-run deploy (secrets), verify `X-Forwarded-*` are set by Caddy |
| Twilio shows `12300` | webhook response without Content-Type | our endpoints answer TwiML; check the API version deployed |
| Messages not delivered (`63015`) | recipient never joined the sandbox | have the employee send `join <code>` to the sandbox number |
| Agent answers like the old parser (literal "SÍ"/"]" only) | `logs worker \| grep llm_disabled` | fix the reason: missing `OPENAI_API_KEY`, `LLM_PROVIDER=none`, or the provider SDK not installed in the image (rebuild) |
| LLM cost rising unexpectedly | Langfuse traces, Ops screen | lower `LLM_MAX_TOKENS`, switch to a cheaper model, or set `LLM_PROVIDER=none` to stop spending |
| No traces in Langfuse though the app works | `logs api \| grep tracing` | keys absent (logs `tracing_disabled`), wrong region host, or keys from another project |
| `20003 Primary compliance profile` | Twilio Trust Hub profile `draft` | complete and submit the profile in Trust Hub |
| Rescue looks stuck (no wave, no escalation) | `logs worker \| grep reconcile_stale_cases_recovered`; `docker compose ps` (worker and beat up?) | the reconcile sweep re-enqueues overdue deadline timers every 60 s, so a stuck case escalates within a minute of beat running; if it does not, check worker/beat are up and Redis is reachable — do not re-run the flow first |
| Message gets no reply | see §4 checklist | API enqueues (`twilio_inbound_received`), worker processes (`worker_inbound_processed`); a `twilio_inbound_enqueue_failed` 500 means Redis/broker down — Twilio retries, recover Redis |
| Timeouts/purge never fire | `docker compose ps` shows `beat` down | start beat: `docker compose up -d beat` — beat owns `run-due-jobs` (every 5 s) and the daily purge |
| DB full / slow | `df -h`, `docker system df` | prune images (`docker image prune -f`), grow the EBS volume |

## 7. Rollback

```bash
# Images are tagged with the commit SHA: deploy the previous tag.
ssh ubuntu@<host> 'cd /opt/shift-rescue && ./deploy/remote-deploy.sh <previous-sha>'
```

Database migrations are additive so far; for a destructive migration restore
the EBS snapshot (see Backups).

## 8. Backups and retention

- Postgres lives in the `pgdata` volume on the instance's EBS volume. Take an
  EBS snapshot before risky changes.
- Message bodies are redacted and purged by the retention job (spec §10).
- Langfuse Cloud keeps traces per its free-tier retention.

## 9. Costs

t3.large on-demand in eu-west-1 ≈ **$61/month** (see ADR-003 for the
comparison with self-hosting Langfuse), plus EBS (~$8/month for 100 GB gp3),
Elastic IP while attached (free) and ECR storage (cents). Twilio sandbox usage
inside the free trial/upgraded account is free for joined numbers.

LLM inference is usage-based and small at demo volume: `gpt-4o-mini` at
$0.15/M input and $0.60/M output tokens, with interpretation calls of a few
hundred tokens each — cents per hundred messages. Langfuse Cloud free tier
covers the demo's trace volume. Cost per rescue is visible in Langfuse and in
the dashboard's Ops screen.

Stop the instance when the demo is not being reviewed:

```bash
aws ec2 stop-instances --instance-ids <id>   # restart later, data survives
```
