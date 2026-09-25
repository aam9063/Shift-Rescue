# Feature: Deployment and delivery (`deploy-delivery`)

Status: **in progress**
Branch: `feature/deploy-delivery` (from `dev` after the whatsapp-channel merge)
Created: 2026-09-25

## Objective

Deliver spec Feature 8: the demo running on AWS from GitHub Actions, with
`docker-compose.prod.yml`, Caddy (automatic TLS), images in ECR, secrets in SSM
Parameter Store, OIDC-based CI auth, runbook, business-oriented README,
`docs/eval-report.md`, the demo video script — and ADR-003 recording the
deployment decisions, including the user's late instruction: **Langfuse Cloud
(no self-hosted Langfuse), t3.large** (see `docs/assumptions.md` A4).

## Context and decisions (user-confirmed)

| Decision | Value |
|---|---|
| Compute | Single **t3.large** (2 vCPU / 8 GB) EC2 instance, Docker Compose |
| TLS / ingress | **Caddy** with automatic Let's Encrypt certificates |
| Domain | None purchased → **sslip.io** (`<ip-with-dashes>.sslip.io` resolves to the Elastic IP) |
| Observability | **Langfuse Cloud** via OTLP env vars — no Langfuse containers on the instance |
| Secrets | SSM Parameter Store (SecureString) fetched at deploy time to the instance's `.env` |
| Images | ECR (api/worker/beat share one image; frontend built into the Caddy image) |
| CI auth | GitHub Actions OIDC role (no long-lived AWS keys in the repo) |
| Tooling | AWS CLI v2 on the maintainer's machine (scoop), commands run with the user's approval |

## Scope

- `infra/docker-compose.prod.yml`: postgres, redis, api, worker, beat, caddy.
- `infra/Caddyfile`: TLS + reverse proxy (`/` → SPA, `/api` + `/webhooks` + `/ws` → API).
- `backend/Dockerfile` (existing) + `frontend/Dockerfile.prod` (build + static serve via Caddy image).
- `.github/workflows/deploy.yml`: build → push to ECR → deploy over SSH (fetch secrets from SSM, pull, migrate, up).
- `infra/deploy/bootstrap-ec2.sh`: one-shot instance bootstrap (Docker, compose plugin, Caddy dirs, swap).
- `docs/adr/ADR-003-deployment-aws.md`, `docs/runbook.md`, `docs/eval-report.md`, `docs/demo-script.md`, README section.

Out of scope: managed services migration (documented as the production path in
ADR-003), multi-environment pipelines, blue/green deploys.

## Acceptance criteria

- [ ] AC1: `docker-compose.prod.yml` + Caddyfile validate and describe the documented stack (no Langfuse containers).
- [ ] AC2: Production frontend image builds the SPA and Caddy serves it with the API proxied.
- [ ] AC3: Deploy workflow builds and pushes both images to ECR and deploys on the instance.
- [ ] AC4: Instance bootstrapped (Docker + compose), secrets loaded from SSM, stack running with TLS.
- [ ] AC5: Public URL serves the dashboard, `/api` health passes, and the Twilio webhook points to the instance (no tunnel).
- [ ] AC6: ADR-003, runbook, README, eval-report and demo script written.
- [ ] AC7: Work-unit commits recorded.

## Tasks

- [ ] T1 — Compose prod + Caddyfile + frontend prod image (+ validation).
- [ ] T2 — Deploy workflow (ECR + OIDC + SSH) + EC2 bootstrap script.
- [ ] T3 — AWS bootstrap with the user: IAM, ECR, OIDC role, security group, key pair, EC2 + Elastic IP, SSM secrets.
- [ ] T4 — First deploy + verification (TLS, health, dashboard, Twilio webhook switch).
- [ ] T5 — Docs: ADR-003, runbook, README, eval-report, demo script; close feature.

## Verification evidence

(appended per task)

## Commits

(appended per commit)

## Progress / Next step

Next: T1 (repo artifacts).
