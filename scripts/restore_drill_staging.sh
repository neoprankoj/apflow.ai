#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.staging}"
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.staging.yml)
export APFLOW_ENV_FILE="$ENV_FILE"

BACKUP_FILE="${1:-}"
RESTORE_DB="${RESTORE_DB:-apflow_restore_drill_$(date -u +%Y%m%dT%H%M%SZ)}"
KEEP_RESTORE_DB="${KEEP_RESTORE_DB:-false}"
RESTORE_DB_CREATED="false"

if [[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]]; then
  echo "Usage: scripts/restore_drill_staging.sh backups/apflow-postgres-YYYYMMDDTHHMMSSZ.dump" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Run this on the staging host or set ENV_FILE to the correct env file." >&2
  exit 1
fi

if [[ ! "$RESTORE_DB" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "Unsafe RESTORE_DB value. Use only letters, numbers, and underscores." >&2
  exit 1
fi

cleanup() {
  if [[ "$RESTORE_DB_CREATED" == "true" && "$KEEP_RESTORE_DB" != "true" ]]; then
    echo "Dropping temporary restore database $RESTORE_DB"
    docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres sh -lc \
      'dropdb -U "${POSTGRES_USER:-apflow}" --if-exists "$1"' sh "$RESTORE_DB" >/dev/null || true
  elif [[ "$RESTORE_DB_CREATED" == "true" ]]; then
    echo "Keeping temporary restore database $RESTORE_DB because KEEP_RESTORE_DB=true"
  fi
}
trap cleanup EXIT

echo "Running non-destructive restore drill into temporary database $RESTORE_DB"
echo "Backup file: $BACKUP_FILE"
ls -lh "$BACKUP_FILE"

docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres sh -lc \
  'createdb -U "${POSTGRES_USER:-apflow}" "$1"' sh "$RESTORE_DB"
RESTORE_DB_CREATED="true"

docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres sh -lc \
  'pg_restore -U "${POSTGRES_USER:-apflow}" -d "$1"' sh "$RESTORE_DB" < "$BACKUP_FILE"

echo "Verifying restored schema in $RESTORE_DB"
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres sh -lc \
  'psql -U "${POSTGRES_USER:-apflow}" -d "$1" -v ON_ERROR_STOP=1 -c "\dt" -c "select count(*) as table_count from information_schema.tables where table_schema = '\''public'\'';"' sh "$RESTORE_DB"

echo "Restore drill completed successfully."
