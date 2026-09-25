#!/usr/bin/env bash
# Runs ON the EC2 instance (invoked by .github/workflows/deploy.yml over SSH).
#
#   ./remote-deploy.sh <image-tag>
#
# Steps: load secrets from SSM Parameter Store into .env -> log in to ECR ->
# pull images -> apply migrations -> seed demo data -> bring the stack up.
set -euo pipefail

IMAGE_TAG="${1:-latest}"
APP_DIR="${APP_DIR:-/opt/shift-rescue}"
AWS_REGION="${AWS_REGION:-eu-west-1}"
SSM_PREFIX="${SSM_PREFIX:-/shift-rescue/prod}"
COMPOSE="docker compose -f ${APP_DIR}/docker-compose.prod.yml --env-file ${APP_DIR}/.env"

cd "$APP_DIR"

echo "==> Loading secrets from SSM (${SSM_PREFIX}) into .env"
: >"${APP_DIR}/.env"
chmod 600 "${APP_DIR}/.env"

# Non-secret values that must exist in .env for compose interpolation.
{
	echo "IMAGE_TAG=${IMAGE_TAG}"
	echo "ECR_REGISTRY=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.${AWS_REGION}.amazonaws.com"
} >>"${APP_DIR}/.env"

for name in $(aws ssm get-parameters-by-path --path "${SSM_PREFIX}" --recursive \
	--with-decryption --region "${AWS_REGION}" \
	--query 'Parameters[].Name' --output text); do
	key="$(basename "$name")"
	value="$(aws ssm get-parameter --name "$name" --with-decryption \
		--region "${AWS_REGION}" --query 'Parameter.Value' --output text)"
	# Escape newlines so the value stays on one line in .env
	printf '%s=%s\n' "$key" "${value//$'\n'/\\n}" >>"${APP_DIR}/.env"
done

echo "==> Checking required variables"
for required in DOMAIN POSTGRES_PASSWORD JWT_SECRET; do
	if ! grep -q "^${required}=..*" "${APP_DIR}/.env"; then
		echo "Missing required value in .env: ${required}" >&2
		exit 1
	fi
done

echo "==> Logging in to ECR"
aws ecr get-login-password --region "${AWS_REGION}" |
	docker login --username AWS --password-stdin "$(grep '^ECR_REGISTRY=' "${APP_DIR}/.env" | cut -d= -f2)"

echo "==> Pulling images (tag ${IMAGE_TAG})"
$COMPOSE pull

echo "==> Applying database migrations and seeding"
$COMPOSE up -d postgres redis
sleep 5
$COMPOSE run --rm api uv run --no-dev python -m app.db.seed_cli

echo "==> Bringing the stack up"
$COMPOSE up -d --remove-orphans

echo "==> Health check"
sleep 8
$COMPOSE exec -T api curl -fsS http://localhost:8000/health || {
	echo "API health check failed" >&2
	$COMPOSE logs --tail 40 api >&2
	exit 1
}

echo "Deploy complete: https://$(grep '^DOMAIN=' "${APP_DIR}/.env" | cut -d= -f2)"
