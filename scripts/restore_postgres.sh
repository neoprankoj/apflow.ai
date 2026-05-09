#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.staging}"
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.staging.yml)
export APFLOW_ENV_FILE="$ENV_FILE"

BACKUP_FILE="${1:-}"
CONFIRM="${2:---dry-run}"

if [[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]]; then
  echo "Usage: scripts/restore_postgres.sh backups/apflow.sql --yes" >&2
  exit 1
fi

if [[ "$CONFIRM" != "--yes" ]]; then
  echo "Dry run only. Restore is destructive." >&2
  echo "Backup file: $BACKUP_FILE"
  ls -lh "$BACKUP_FILE"
  echo "Re-run with --yes to stop API/web, drop and recreate the apflow database, then restore." >&2
  exit 1
fi

echo "WARNING: destructive restore requested for $BACKUP_FILE"
echo "Stopping API and web before restore..."
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" stop api web

echo "Dropping and recreating apflow database..."
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres \
  psql -U apflow -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS apflow WITH (FORCE);" \
  -c "CREATE DATABASE apflow OWNER apflow;"

echo "Restoring $BACKUP_FILE"
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres \
  psql -U apflow -d apflow -v ON_ERROR_STOP=1 < "$BACKUP_FILE"

echo "Starting API and web..."
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" up -d api web

echo "Restore complete."
