#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.staging}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.staging.yml)
export APFLOW_ENV_FILE="$ENV_FILE"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${1:-$BACKUP_DIR/apflow-$STAMP.sql}"

mkdir -p "$(dirname "$OUT_FILE")"

echo "Writing PostgreSQL backup to $OUT_FILE"
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" exec -T postgres \
  pg_dump -U apflow -d apflow --clean --if-exists > "$OUT_FILE"

if [[ ! -s "$OUT_FILE" ]]; then
  echo "Backup file is empty: $OUT_FILE" >&2
  exit 1
fi

echo "Backup complete: $OUT_FILE"
ls -lh "$OUT_FILE"
