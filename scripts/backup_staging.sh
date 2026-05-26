#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.staging}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
DB_USER="${APFLOW_BACKUP_DB_USER:-app_user}"
DB_NAME="${APFLOW_BACKUP_DB_NAME:-apflow}"
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.staging.yml)
export APFLOW_ENV_FILE="$ENV_FILE"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${1:-$BACKUP_DIR/apflow-postgres-$STAMP.dump}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Run this on the staging host or set ENV_FILE to the correct env file." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT_FILE")"
PARTIAL_FILE="$OUT_FILE.partial"
rm -f "$PARTIAL_FILE"

echo "Verifying PostgreSQL connection for database $DB_NAME as user $DB_USER"
if ! docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres sh -lc \
  'psql -U "$1" -d "$2" -v ON_ERROR_STOP=1 -c "select current_user, current_database();"' sh "$DB_USER" "$DB_NAME"; then
  echo "Backup aborted: cannot connect to database $DB_NAME as user $DB_USER." >&2
  echo "Set APFLOW_BACKUP_DB_USER and APFLOW_BACKUP_DB_NAME if staging uses a different initialized DB role/name." >&2
  exit 1
fi

echo "Writing PostgreSQL custom-format backup to $OUT_FILE"
if ! docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres sh -lc \
  'pg_dump -U "$1" -d "$2" -Fc' sh "$DB_USER" "$DB_NAME" > "$PARTIAL_FILE"; then
  rm -f "$PARTIAL_FILE"
  echo "Backup failed. Incomplete dump was deleted." >&2
  exit 1
fi

if [[ ! -s "$PARTIAL_FILE" ]]; then
  rm -f "$PARTIAL_FILE"
  echo "Backup file is empty: $OUT_FILE" >&2
  exit 1
fi

mv "$PARTIAL_FILE" "$OUT_FILE"

echo "Backup complete: $OUT_FILE"
ls -lh "$OUT_FILE"

if command -v file >/dev/null 2>&1; then
  file "$OUT_FILE" || true
fi
