#!/usr/bin/env bash
set -u

if [[ -d /usr/bin ]]; then
  PATH="/usr/bin:/bin:$PATH"
fi

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
if [[ "$SCRIPT_DIR" == "${BASH_SOURCE[0]}" ]]; then
  SCRIPT_DIR="."
fi

ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR" || exit 1

BACKUP_DIR="${APFLOW_BACKUP_DIR:-backups}"
WARN_HOURS="${APFLOW_BACKUP_WARN_HOURS:-24}"
CRITICAL_HOURS="${APFLOW_BACKUP_CRITICAL_HOURS:-72}"

is_non_negative_integer() {
  [[ "$1" =~ ^[0-9]+$ ]]
}

if ! is_non_negative_integer "$WARN_HOURS"; then
  echo "FAIL: APFLOW_BACKUP_WARN_HOURS must be a non-negative integer." >&2
  exit 1
fi

if ! is_non_negative_integer "$CRITICAL_HOURS"; then
  echo "FAIL: APFLOW_BACKUP_CRITICAL_HOURS must be a non-negative integer." >&2
  exit 1
fi

if (( CRITICAL_HOURS < WARN_HOURS )); then
  echo "FAIL: APFLOW_BACKUP_CRITICAL_HOURS must be greater than or equal to APFLOW_BACKUP_WARN_HOURS." >&2
  exit 1
fi

echo "Backup directory: $BACKUP_DIR"
echo "Warning threshold: ${WARN_HOURS}h"
echo "Critical threshold: ${CRITICAL_HOURS}h"

if [[ ! -d "$BACKUP_DIR" ]]; then
  echo "CRITICAL: backup directory does not exist: $BACKUP_DIR"
  exit 1
fi

LATEST_BACKUP="$(
  find "$BACKUP_DIR" -maxdepth 1 -type f -name '*.dump' ! -name '*.partial' -size +0c -printf '%T@ %s %p\n' 2>/dev/null |
    sort -nr |
    head -n 1 || true
)"

if [[ -z "$LATEST_BACKUP" ]]; then
  ZERO_BYTE_COUNT="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name '*.dump' ! -name '*.partial' -size 0c 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$ZERO_BYTE_COUNT" != "0" ]]; then
    echo "CRITICAL: only zero-byte backup dump files were found. Zero-byte dumps are invalid."
  else
    echo "CRITICAL: no valid non-empty backups/*.dump file found."
  fi
  exit 1
fi

BACKUP_EPOCH="${LATEST_BACKUP%% *}"
REST="${LATEST_BACKUP#* }"
BACKUP_SIZE="${REST%% *}"
BACKUP_FILE="${REST#* }"
NOW_EPOCH="$(date +%s)"
BACKUP_SECONDS="${BACKUP_EPOCH%.*}"
BACKUP_AGE_SECONDS=$((NOW_EPOCH - BACKUP_SECONDS))
BACKUP_AGE_HOURS=$((BACKUP_AGE_SECONDS / 3600))

echo "Latest backup: $BACKUP_FILE"
echo "Latest backup size: $BACKUP_SIZE bytes"
echo "Latest backup age: ${BACKUP_AGE_HOURS}h"

if (( BACKUP_AGE_HOURS > CRITICAL_HOURS )); then
  echo "CRITICAL: latest valid backup is older than ${CRITICAL_HOURS}h."
  exit 1
fi

if (( BACKUP_AGE_HOURS > WARN_HOURS )); then
  echo "WARN: latest valid backup is older than ${WARN_HOURS}h."
  exit 0
fi

echo "OK: latest valid backup is within ${WARN_HOURS}h."
exit 0
