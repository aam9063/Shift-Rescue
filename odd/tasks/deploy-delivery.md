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

**Repo artifacts complete (T1, T2, docs).** T3/T4 (AWS instance + first deploy)
are **deferred by user decision** to avoid the monthly cost until the demo is
reviewed; the free infrastructure is already created.

### Already created in AWS (no cost)

| Resource | Value |
|---|---|
| ECR | `shift-rescue-api`, `shift-rescue-web` (`786016560269.dkr.ecr.eu-west-1.amazonaws.com/...`) |
| GitHub OIDC provider | `token.actions.githubusercontent.com` |
| Deploy role (CI) | `arn:aws:iam::786016560269:role/shift-rescue-github-deploy` (trusts `repo:aam9063/Shift-Rescue:ref:refs/heads/main`, ECR push) |
| Instance role/profile | `shift-rescue-instance` (ECR pull + `ssm:GetParameter*` on `/shift-rescue/prod/*`) |
| Security group | `sg-0355bef505718a4d2` (80/443 public, 22 from `79.117.226.228`) |
| SSH key pair | local `~/.ssh/shift-rescue-deploy`, imported as `shift-rescue-deploy` |
| Region | `eu-west-1` |

### Resume plan (≈10 minutes when the user approves the cost)

1. Launch the instance and attach the Elastic IP:

   ```bash
   SG=sg-0355bef505718a4d2; REGION=eu-west-1
   AMI=$(aws ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id --region $REGION --query 'Parameter.Value' --output text)
   IID=$(aws ec2 run-instances --image-id $AMI --instance-type t3.large      --key-name shift-rescue-deploy --security-group-ids $SG      --iam-instance-profile Name=shift-rescue-instance      --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3}'      --user-data file://infra/deploy/bootstrap-ec2.sh      --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=shift-rescue-demo}]'      --region $REGION --query 'Instances[0].InstanceId' --output text)
   aws ec2 wait instance-running --instance-ids $IID --region $REGION
   EIP=$(aws ec2 allocate-address --domain vpc --region $REGION --query 'AllocationId' --output text)
   aws ec2 associate-address --instance-id $IID --allocation-id $EIP --region $REGION
   aws ec2 describe-addresses --allocation-ids $EIP --region $REGION --query 'Addresses[0].PublicIp' --output text
   ```

2. Store the secrets (DOMAIN = the Elastic IP with dashes + `.sslip.io`):

   ```bash
   P=/shift-rescue/prod; REGION=eu-west-1
   aws ssm put-parameter --name $P/DOMAIN          --value '1-2-3-4.sslip.io' --type String         --overwrite --region $REGION
   aws ssm put-parameter --name $P/POSTGRES_PASSWORD --value "$(openssl rand -hex 24)" --type SecureString --overwrite --region $REGION
   aws ssm put-parameter --name $P/JWT_SECRET      --value "$(openssl rand -hex 32)" --type SecureString --overwrite --region $REGION
   aws ssm put-parameter --name $P/TWILIO_ACCOUNT_SID  --value 'AC…' --type SecureString --overwrite --region $REGION
   aws ssm put-parameter --name $P/TWILIO_AUTH_TOKEN   --value '…'   --type SecureString --overwrite --region $REGION
   aws ssm put-parameter --name $P/TWILIO_WHATSAPP_FROM --value 'whatsapp:+14155238886' --type String --overwrite --region $REGION
   ```

3. Repository secrets for the workflow: `AWS_DEPLOY_ROLE_ARN`
   (`arn:aws:iam::786016560269:role/shift-rescue-github-deploy`), `EC2_HOST`
   (the Elastic IP), `EC2_USER` (`ubuntu`), `EC2_SSH_KEY`
   (`~/.ssh/shift-rescue-deploy`, the private key).
4. Merge this branch to `main` and run **Actions → Deploy demo**.
5. Point the Twilio sandbox webhook at
   `https://<domain>/webhooks/twilio/inbound` (no tunnel needed any more).
6. When the review is over: `aws ec2 stop-instances --instance-ids $IID`
   (only the EBS volume keeps costing) or terminate + release the EIP.
