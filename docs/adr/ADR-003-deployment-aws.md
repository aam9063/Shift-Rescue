# ADR-003: Demo deployment on AWS (single EC2 + Langfuse Cloud)

Status: accepted
Date: 2026-09-25
Deciders: FDE + product owner
Related: spec §15, ADR-001, `docs/assumptions.md` A4, Feature `deploy-delivery`

## Context

The MVP needs a public, TLS-secured demo the reviewer can open: dashboard,
API, and the Twilio WhatsApp webhook. The stack needs **persistent workers**
(Celery worker + beat) and a database, so a serverless-only approach is not
enough for the demo. Observability (spec §9.1) originally assumed a
self-hosted Langfuse, which brings ClickHouse, its own Postgres and Redis.

The product owner's late instruction fixed two decisions:

> Use **Langfuse Cloud** (free tier) instead of self-hosting. Do not deploy
> Langfuse's own Postgres/ClickHouse/Redis on the instance; only configure
> `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_HOST` so the
> OpenTelemetry SDK exports there. Size the instance as **t3.large**
> (2 vCPU, 8 GB), not t3.xlarge.

## Decision

| Layer | Choice | Rationale |
|---|---|---|
| Compute | One EC2 **t3.large** (Ubuntu 24.04), Docker Compose | Celery needs long-running processes; a single box is the cheapest shape that runs them. No build happens on the instance (images are built in CI), so 2 vCPU / 8 GB is plenty. |
| Ingress / TLS | **Caddy 2** with automatic Let's Encrypt | One container, automatic certificates, HTTP→HTTPS redirect, sane security headers, JSON access logs. |
| Domain | **sslip.io** (`<ip-with-dashes>.sslip.io`) | No domain purchase needed: the wildcard DNS resolves to the Elastic IP and Caddy obtains a valid certificate. Swapping to a real domain later is one `.env` value. |
| Images | **ECR**, one image for api/worker/beat and one for the web (SPA + Caddy) | Same artefact promoted, no registry credentials on the instance (instance role pulls). |
| Secrets | **SSM Parameter Store** (SecureString) → `.env` at deploy time | Nothing sensitive in the repository, GitHub secrets hold only the deploy role and SSH key. |
| CI auth | **GitHub Actions OIDC** role | No long-lived AWS keys in the repo; the role trusts only this repo. |
| Observability | **Langfuse Cloud** over OTLP | Removes three containers (Langfuse, ClickHouse, Langfuse Postgres) and their operational burden. |
| Database / cache | PostgreSQL 16 and Redis containers on the same instance | Demo-scale only; the production path is managed (below). |

## Savings from not self-hosting Langfuse

Self-hosted Langfuse needs the application container **plus ClickHouse plus its
own Postgres** (and Redis for queues) on the box:

| | Self-hosted Langfuse | Langfuse Cloud (this ADR) |
|---|---|---|
| Containers on the instance | 6 app/infra + 3 Langfuse | 6 |
| RAM headroom needed | ~8 GB just for ClickHouse + Langfuse | ~2 GB |
| Instance size | **t3.xlarge** (4 vCPU / 16 GB) | **t3.large** (2 vCPU / 8 GB) |
| On-demand cost (eu-west-1, reference) | ~$0.1664/h ≈ **$121/month** | ~$0.0832/h ≈ **$61/month** |
| Upgrades / backups of the telemetry store | ours | Langfuse's |
| Traces in the demo | local only | shareable URL per trace |

Roughly **half the compute cost**, one fewer stateful system to operate, and
trace links that a reviewer can open. Langfuse's free tier is enough for a
demo's trace volume; if the project grows, the paid tier is still cheaper than
the extra instance size.

## Consequences

- `docker-compose.prod.yml` contains only: postgres, redis, api, worker, beat,
  caddy. The observability path is pure configuration (`LANGFUSE_*`, OTLP).
- The instance stays disposable: everything is recreated by the deploy
  workflow (images from ECR, secrets from SSM, one volume for Postgres).
- Postgres data is not backed up beyond the EBS volume — acceptable for a demo,
  documented in the runbook.
- **Production path** (documented, not built): ECS Fargate for api/worker/beat,
  RDS for PostgreSQL, ElastiCache for Redis, ALB + ACM instead of Caddy, and
  the same ECR images. The adapters and ports already isolate the domain from
  these choices.
- Twilio now points at a **stable HTTPS URL** (`https://<domain>/webhooks/twilio/inbound`),
  so the development tunnel is no longer needed.
