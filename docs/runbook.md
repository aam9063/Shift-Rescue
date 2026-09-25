# Runbook — Shift Rescue demo

Everything a maintainer needs to deploy, smoke-test, debug and roll back the
demo environment (single EC2 instance + Langfuse Cloud, see ADR-003).

## 1. What runs where

| Piece | Where |
|---|---|
| Dashboard (SPA) | EC2 container `caddy`, served from `/srv`, TLS by Let's Encrypt |
| API + Twilio webhooks | EC2 container `api` (proxied by Caddy at `/api`, `/webhooks`) |
| Celery worker + beat | EC2 containers `worker`, `beat` |
| PostgreSQL + Redis | EC2 containers, EBS-backed volume |
| LLM + traces | Anthropic/NaN APIs and **Langfuse Cloud** (external) |
| Images | ECR (`shift-rescue-api`, `shift-rescue-web`) |
| Secrets | SSM Parameter Store under `/shift-rescue/prod/*` |

## 2. Deploy

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

## 3. Smoke test

```bash
curl -fsS https://<domain>/api/../health        # {"status":"ok"...}
curl -fsS -o /dev/null -w '%{http_code}\n' https://<domain>/   # 200 (SPA)
# Twilio: send "hola" from a joined phone; the API log must show
#   twilio_inbound_received ... recognized=true
```

## 4. Common operations

| Task | Command (on the instance, in `/opt/shift-rescue`) |
|---|---|
| Logs (all / one service) | `docker compose -f docker-compose.prod.yml logs -f [api]` |
| Recreate after config change | `docker compose -f docker-compose.prod.yml up -d` |
| Re-seed demo data | `docker compose -f docker-compose.prod.yml run --rm api uv run --no-dev python -m app.db.seed_cli` |
| Migrations | `docker compose -f docker-compose.prod.yml run --rm api uv run --no-dev python -m alembic upgrade head` |
| Update a secret | `aws ssm put-parameter --name /shift-rescue/prod/X --value '...' --type SecureString --overwrite` then re-run the deploy workflow |
| Pause the agent | Settings screen (or `PATCH /api/locations/<id>/settings`) |
| Rotate the SSH key | create a new key pair, add the public key to `~/.ssh/authorized_keys`, update the `EC2_SSH_KEY` secret |

## 5. Incident playbook

| Symptom | First checks | Fix |
|---|---|---|
| 502 from Caddy | `logs caddy`, `logs api` | api container unhealthy → check `.env` (DATABASE_URL) and `logs api` |
| Dashboard blank | `logs caddy` (404 on assets?) | rebuild the web image (`frontend/Dockerfile.prod`) and redeploy |
| Twilio webhook returns 403 | `TWILIO_AUTH_TOKEN` mismatch, or the request did not come through Caddy | re-run deploy (secrets), verify `X-Forwarded-*` are set by Caddy |
| Twilio shows `12300` | webhook response without Content-Type | our endpoints answer TwiML; check the API version deployed |
| Messages not delivered (`63015`) | recipient never joined the sandbox | have the employee send `join <code>` to the sandbox number |
| `20003 Primary compliance profile` | Twilio Trust Hub profile `draft` | complete and submit the profile in Trust Hub |
| Rescue stuck in OFFERING | `logs api \| grep scheduler` | the lifespan ticker drives timeouts; if the API was restarted mid-flight, re-run the flow (in-memory scheduler) |
| DB full / slow | `df -h`, `docker system df` | prune images (`docker image prune -f`), grow the EBS volume |

## 6. Rollback

```bash
# Images are tagged with the commit SHA: deploy the previous tag.
ssh ubuntu@<host> 'cd /opt/shift-rescue && ./deploy/remote-deploy.sh <previous-sha>'
```

Database migrations are additive so far; for a destructive migration restore
the EBS snapshot (see Backups).

## 7. Backups and retention

- Postgres lives in the `pgdata` volume on the instance's EBS volume. Take an
  EBS snapshot before risky changes.
- Message bodies are redacted and purged by the retention job (spec §10).
- Langfuse Cloud keeps traces per its free-tier retention.

## 8. Costs

t3.large on-demand in eu-west-1 ≈ **$61/month** (see ADR-003 for the
comparison with self-hosting Langfuse), plus EBS (~$8/month for 100 GB gp3),
Elastic IP while attached (free) and ECR storage (cents). Twilio sandbox usage
inside the free trial/upgraded account is free for joined numbers.

Stop the instance when the demo is not being reviewed:

```bash
aws ec2 stop-instances --instance-ids <id>   # restart later, data survives
```
