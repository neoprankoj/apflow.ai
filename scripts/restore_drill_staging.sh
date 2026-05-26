#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.staging}"
DB_USER="${APFLOW_BACKUP_DB_USER:-app_user}"
DB_NAME="${APFLOW_BACKUP_DB_NAME:-apflow}"
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

if [[ ! -s "$BACKUP_FILE" ]]; then
  echo "Backup file is empty or unreadable: $BACKUP_FILE" >&2
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

if [[ "$RESTORE_DB" == "$DB_NAME" ]]; then
  echo "Unsafe RESTORE_DB value: restore target must not be the active database $DB_NAME." >&2
  exit 1
fi

cleanup() {
  if [[ "$RESTORE_DB_CREATED" == "true" && "$KEEP_RESTORE_DB" != "true" ]]; then
    echo "Dropping temporary restore database $RESTORE_DB"
    docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres sh -lc \
      'dropdb -U "$1" --if-exists "$2"' sh "$DB_USER" "$RESTORE_DB" >/dev/null || true
  elif [[ "$RESTORE_DB_CREATED" == "true" ]]; then
    echo "Keeping temporary restore database $RESTORE_DB because KEEP_RESTORE_DB=true"
  fi
}
trap cleanup EXIT

echo "Verifying PostgreSQL connection for database $DB_NAME as user $DB_USER"
if ! docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres sh -lc \
  'psql -U "$1" -d "$2" -v ON_ERROR_STOP=1 -c "select current_user, current_database();"' sh "$DB_USER" "$DB_NAME"; then
  echo "Restore drill aborted: cannot connect to database $DB_NAME as user $DB_USER." >&2
  echo "Set APFLOW_BACKUP_DB_USER and APFLOW_BACKUP_DB_NAME if staging uses a different initialized DB role/name." >&2
  exit 1
fi

echo "Running non-destructive restore drill into temporary database $RESTORE_DB"
echo "Backup file: $BACKUP_FILE"
ls -lh "$BACKUP_FILE"

docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres sh -lc \
  'createdb -U "$1" "$2"' sh "$DB_USER" "$RESTORE_DB"
RESTORE_DB_CREATED="true"

docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres sh -lc \
  'pg_restore -U "$1" -d "$2"' sh "$DB_USER" "$RESTORE_DB" < "$BACKUP_FILE"

echo "Verifying restored schema in $RESTORE_DB"
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres sh -lc \
  'psql -U "$1" -d "$2" -v ON_ERROR_STOP=1 -c "\dt" -c "select count(*) as table_count from information_schema.tables where table_schema = '\''public'\'';"' sh "$DB_USER" "$RESTORE_DB"

echo "Restore drill completed successfully."
