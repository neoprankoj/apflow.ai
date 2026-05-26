#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.staging}"
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.staging.yml)
WATCH_PORTS=("3000" "8000" "5432" "6379" "9000" "9001")

section() {
  printf '\n== %s ==\n' "$1"
}

run_optional() {
  local label="$1"
  shift
  section "$label"
  if ! "$@"; then
    echo "Command unavailable or failed: $*" >&2
  fi
}

section "Docker Compose services"
if [[ -f "$ENV_FILE" ]]; then
  APFLOW_ENV_FILE="$ENV_FILE" docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" ps || true
else
  echo "Missing $ENV_FILE; showing default compose project instead."
  docker compose ps || true
fi

run_optional "Docker published ports" docker ps --format 'table {{.Names}}\t{{.Ports}}'
run_optional "Listening sockets" ss -tulpn

section "UFW status"
if command -v ufw >/dev/null 2>&1; then
  sudo ufw status verbose || ufw status verbose || true
else
  echo "ufw is not installed or not on PATH."
fi

section "Public bind warnings"
PORT_OUTPUT="$(docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null || true)"
SS_OUTPUT="$(ss -tulpn 2>/dev/null || true)"

for port in "${WATCH_PORTS[@]}"; do
  if printf '%s\n%s\n' "$PORT_OUTPUT" "$SS_OUTPUT" | grep -E "(0\.0\.0\.0|:::|\[::\]):$port(->|[[:space:]]|,)" >/dev/null 2>&1; then
    echo "WARNING: port $port appears bound on all interfaces. Review before public Domain + HTTPS."
  fi
done

echo "Read-only inspection complete. No firewall or iptables changes were made."
