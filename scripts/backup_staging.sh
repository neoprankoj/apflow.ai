#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.staging}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.staging.yml)
export APFLOW_ENV_FILE="$ENV_FILE"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${1:-$BACKUP_DIR/apflow-postgres-$STAMP.dump}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Run this on the staging host or set ENV_FILE to the correct env file." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT_FILE")"

echo "Writing PostgreSQL custom-format backup to $OUT_FILE"
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres sh -lc \
  'pg_dump -U "${POSTGRES_USER:-apflow}" -d "${POSTGRES_DB:-apflow}" -Fc' \
  > "$OUT_FILE"

if [[ ! -s "$OUT_FILE" ]]; then
  echo "Backup file is empty: $OUT_FILE" >&2
  exit 1
fi

echo "Backup complete: $OUT_FILE"
ls -lh "$OUT_FILE"

if command -v file >/dev/null 2>&1; then
  file "$OUT_FILE" || true
fi
