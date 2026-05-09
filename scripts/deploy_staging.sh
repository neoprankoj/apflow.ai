#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.staging}"
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.staging.yml)
export APFLOW_ENV_FILE="$ENV_FILE"
COMPOSE_ARGS=("${COMPOSE_FILES[@]}" --env-file "$ENV_FILE")
if [[ "${PROXY:-false}" == "true" || "${PROXY:-false}" == "1" ]]; then
  COMPOSE_ARGS+=("--profile" "proxy")
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Copy .env.staging.example to $ENV_FILE and replace every secret first." >&2
  exit 1
fi

if grep -q "replace-with" "$ENV_FILE"; then
  echo "$ENV_FILE still contains replace-with placeholders." >&2
  exit 1
fi

echo "Validating Compose configuration..."
docker compose "${COMPOSE_ARGS[@]}" config --quiet

echo "Building and starting staging stack..."
docker compose "${COMPOSE_ARGS[@]}" up --build -d

echo "Current service status:"
docker compose "${COMPOSE_ARGS[@]}" ps

echo "Deployment started. Run scripts/check_staging.sh after DNS/HTTPS is reachable."
