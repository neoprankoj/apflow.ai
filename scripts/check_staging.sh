#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

API_URL="${1:-${APFLOW_API_BASE_URL:-}}"
WEB_URL="${2:-${APFLOW_WEB_BASE_URL:-}}"
ENV_FILE="${ENV_FILE:-.env.staging}"
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.staging.yml)
export APFLOW_ENV_FILE="$ENV_FILE"

if [[ -z "$API_URL" || -z "$WEB_URL" ]]; then
  echo "Usage: scripts/check_staging.sh https://api.example.com https://app.example.com" >&2
  echo "Or set APFLOW_API_BASE_URL and APFLOW_WEB_BASE_URL." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Set ENV_FILE or copy .env.staging.example to .env.staging." >&2
  exit 1
fi

echo "Checking Docker daemon..."
docker info >/dev/null

echo "Checking Compose configuration..."
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" config --quiet

echo "Checking running containers..."
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" ps
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" ps --status running api web postgres redis >/dev/null

echo "Checking PostgreSQL data directory..."
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres \
  sh -c "test -d /var/lib/postgresql/data/base"

echo "Checking disk space..."
df -h .

if docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" ps caddy 2>/dev/null | grep -q "caddy"; then
  echo "Caddy service status:"
  docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" ps caddy
fi

echo "Checking API health and readiness..."
curl -fsS "$API_URL/health" >/dev/null
curl -fsS "$API_URL/ready" >/dev/null

echo "Checking web URL..."
curl -fsS "$WEB_URL" >/dev/null

VERIFY_ARGS=(--api-url "$API_URL" --web-url "$WEB_URL" --auth-enabled)
if [[ -n "${APFLOW_VERIFY_EMAIL:-}" ]]; then
  VERIFY_ARGS+=(--email "$APFLOW_VERIFY_EMAIL")
fi
if [[ -n "${APFLOW_VERIFY_PASSWORD:-}" ]]; then
  VERIFY_ARGS+=(--password "$APFLOW_VERIFY_PASSWORD")
fi
if [[ "${SKIP_UPLOAD:-false}" == "true" || "${SKIP_UPLOAD:-false}" == "1" ]]; then
  VERIFY_ARGS+=(--skip-upload)
fi
if [[ "${SKIP_VENDOR:-false}" == "true" || "${SKIP_VENDOR:-false}" == "1" ]]; then
  VERIFY_ARGS+=(--skip-vendor)
fi

python scripts/verify_runtime.py "${VERIFY_ARGS[@]}"
