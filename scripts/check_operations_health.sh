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

PUBLIC_BASE_URL="${1:-${APFLOW_PUBLIC_BASE_URL:-}}"
ENV_FILE="${ENV_FILE:-.env.staging}"
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.staging.yml)
OK_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

section() {
  printf '\n== %s ==\n' "$1"
}

ok() {
  OK_COUNT=$((OK_COUNT + 1))
  printf 'OK: %s\n' "$1"
}

warn() {
  WARN_COUNT=$((WARN_COUNT + 1))
  printf 'WARN: %s\n' "$1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf 'FAIL: %s\n' "$1"
}

sanitize_base_url() {
  local raw_url="$1"
  local rest
  local scheme

  raw_url="${raw_url%%\?*}"
  raw_url="${raw_url%/}"

  if [[ "$raw_url" == *"://"* ]]; then
    scheme="${raw_url%%://*}://"
    rest="${raw_url#*://}"
    if [[ "$rest" == *"@"* ]]; then
      raw_url="${scheme}${rest#*@}"
    fi
  fi

  printf '%s' "$raw_url"
}

compose_cmd() {
  if [[ -f "$ENV_FILE" ]]; then
    APFLOW_ENV_FILE="$ENV_FILE" docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" "$@"
  else
    docker compose "$@"
  fi
}

curl_status() {
  local url="$1"
  curl -L -sS -o /dev/null --max-time 10 -w '%{http_code}' "$url"
}

curl_head_status() {
  local url="$1"
  curl -I -L -sS -o /dev/null --max-time 10 -w '%{http_code}' "$url"
}

check_http_status() {
  local label="$1"
  local url="$2"
  local expected_pattern="$3"
  local status

  if ! command -v curl >/dev/null 2>&1; then
    warn "curl is not installed; skipping $label."
    return 0
  fi

  status="$(curl_status "$url" 2>/dev/null || true)"
  if [[ -z "$status" || "$status" == "000" ]]; then
    fail "$label is not reachable at $url."
    return 0
  fi

  if [[ "$status" =~ $expected_pattern ]]; then
    ok "$label returned HTTP $status."
  else
    fail "$label returned unexpected HTTP $status from $url."
  fi
}

check_head_status() {
  local label="$1"
  local url="$2"
  local expected_pattern="$3"
  local status

  if ! command -v curl >/dev/null 2>&1; then
    warn "curl is not installed; skipping $label."
    return 0
  fi

  status="$(curl_head_status "$url" 2>/dev/null || true)"
  if [[ -z "$status" || "$status" == "000" ]]; then
    fail "$label is not reachable at $url."
    return 0
  fi

  if [[ "$status" =~ $expected_pattern ]]; then
    ok "$label returned HTTP $status."
  else
    fail "$label returned unexpected HTTP $status from $url."
  fi
}

section "Docker Compose services"
if command -v docker >/dev/null 2>&1; then
  if compose_cmd ps; then
    COMPOSE_OUTPUT="$(compose_cmd ps 2>/dev/null || true)"
    if printf '%s\n' "$COMPOSE_OUTPUT" | grep -Ei '\b(exit|exited|dead|unhealthy|restarting)\b' >/dev/null 2>&1; then
      fail "One or more Docker Compose services appear exited, unhealthy, dead, or restarting."
    else
      ok "Docker Compose services do not show obvious exited/unhealthy state."
    fi
  else
    fail "docker compose ps failed."
  fi
else
  fail "docker is not installed or not on PATH."
fi

section "Local API"
check_http_status "Local API /health" "http://127.0.0.1:8000/health" '^2[0-9][0-9]$'
check_http_status "Local API /ready" "http://127.0.0.1:8000/ready" '^2[0-9][0-9]$'

section "Public proxy"
if [[ -n "$PUBLIC_BASE_URL" ]]; then
  PUBLIC_BASE_URL="$(sanitize_base_url "$PUBLIC_BASE_URL")"
  printf 'Using public base URL: %s\n' "$PUBLIC_BASE_URL"
  check_head_status "Public web" "$PUBLIC_BASE_URL" '^[23][0-9][0-9]$'
  check_http_status "Public API /api/health" "$PUBLIC_BASE_URL/api/health" '^2[0-9][0-9]$'
else
  warn "No APFLOW_PUBLIC_BASE_URL or argument provided; skipping public proxy checks."
fi

section "PostgreSQL readiness"
if command -v docker >/dev/null 2>&1; then
  if compose_cmd exec -T postgres pg_isready -U app_user -d apflow >/dev/null 2>&1; then
    ok "PostgreSQL is ready using app_user/apflow."
  elif compose_cmd exec -T postgres pg_isready -U apflow -d apflow >/dev/null 2>&1; then
    ok "PostgreSQL is ready using apflow/apflow."
  else
    fail "PostgreSQL readiness check failed."
  fi
else
  warn "docker unavailable; skipping PostgreSQL readiness."
fi

section "Disk usage"
if command -v df >/dev/null 2>&1; then
  df -h /
  ROOT_USAGE="$(df -P / 2>/dev/null | awk 'NR==2 {for (i = 1; i <= NF; i++) if ($i ~ /^[0-9]+%$/) {gsub("%","",$i); print $i; exit}}')"
  if [[ "$ROOT_USAGE" =~ ^[0-9]+$ ]]; then
    if (( ROOT_USAGE >= 90 )); then
      fail "Root filesystem usage is ${ROOT_USAGE}% (critical threshold 90%)."
    elif (( ROOT_USAGE >= 75 )); then
      warn "Root filesystem usage is ${ROOT_USAGE}% (warning threshold 75%)."
    else
      ok "Root filesystem usage is ${ROOT_USAGE}%."
    fi
  else
    warn "Could not parse root filesystem usage."
  fi
else
  warn "df is not installed; skipping disk usage."
fi

section "Docker disk usage"
if command -v docker >/dev/null 2>&1; then
  if docker system df; then
    ok "Docker disk usage reported. No cleanup was performed."
  else
    warn "docker system df failed."
  fi
else
  warn "docker unavailable; skipping Docker disk usage."
fi

section "Backup freshness"
if [[ -x scripts/check_backup_age.sh || -f scripts/check_backup_age.sh ]]; then
  if BACKUP_OUTPUT="$(bash scripts/check_backup_age.sh 2>&1)"; then
    printf '%s\n' "$BACKUP_OUTPUT"
    if printf '%s\n' "$BACKUP_OUTPUT" | grep '^WARN:' >/dev/null 2>&1; then
      warn "Backup age check completed with warning."
    else
      ok "Backup age check passed."
    fi
  else
    printf '%s\n' "$BACKUP_OUTPUT"
    fail "Backup age check is critical. Do not continue Domain + HTTPS or pilot data import until a valid fresh backup exists."
  fi
else
  warn "scripts/check_backup_age.sh not found; backup freshness policy could not be checked."
fi

section "Demo reset flag"
if command -v docker >/dev/null 2>&1; then
  API_CONTAINER="${API_CONTAINER:-apflowai-api-1}"
  if ! docker inspect "$API_CONTAINER" >/dev/null 2>&1; then
    FALLBACK_API_CONTAINER="$(compose_cmd ps -q api 2>/dev/null | head -n 1 || true)"
    if [[ -n "$FALLBACK_API_CONTAINER" ]]; then
      API_CONTAINER="$FALLBACK_API_CONTAINER"
    fi
  fi
  DEMO_RESET_LINE="$(docker inspect "$API_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep '^ALLOW_DEMO_RESET=' || true)"
  if [[ -z "$DEMO_RESET_LINE" ]]; then
    warn "ALLOW_DEMO_RESET not found on $API_CONTAINER."
  elif [[ "$DEMO_RESET_LINE" == "ALLOW_DEMO_RESET=false" ]]; then
    ok "ALLOW_DEMO_RESET=false."
  else
    warn "ALLOW_DEMO_RESET is not false on $API_CONTAINER. Current value: ${DEMO_RESET_LINE#ALLOW_DEMO_RESET=}"
  fi
else
  warn "docker unavailable; skipping demo reset flag."
fi

section "Public port inspection"
if [[ -x scripts/check_public_ports.sh || -f scripts/check_public_ports.sh ]]; then
  if bash scripts/check_public_ports.sh; then
    ok "Public port inspection completed."
  else
    warn "Public port inspection returned nonzero; review output above."
  fi
else
  warn "scripts/check_public_ports.sh not found."
fi

section "Reverse proxy inspection"
if [[ -x scripts/check_reverse_proxy.sh || -f scripts/check_reverse_proxy.sh ]]; then
  if [[ -n "$PUBLIC_BASE_URL" ]]; then
    if bash scripts/check_reverse_proxy.sh "$PUBLIC_BASE_URL"; then
      ok "Reverse proxy inspection completed."
    else
      fail "Reverse proxy inspection found clear failures."
    fi
  else
    if bash scripts/check_reverse_proxy.sh; then
      ok "Reverse proxy inspection completed with no public base URL."
    else
      fail "Reverse proxy inspection found clear failures."
    fi
  fi
else
  warn "scripts/check_reverse_proxy.sh not found."
fi

section "Runtime verifier reminder"
if [[ -n "$PUBLIC_BASE_URL" ]]; then
  printf 'Run: python3 scripts/verify_runtime.py --api-url %s/api --web-url %s --auth-enabled\n' "$PUBLIC_BASE_URL" "$PUBLIC_BASE_URL"
else
  printf 'Run: python3 scripts/verify_runtime.py --auth-enabled\n'
fi
warn "Runtime verifier is not run by this health script because it exercises full application workflows."

section "Summary"
printf 'OK: %s\n' "$OK_COUNT"
printf 'WARN: %s\n' "$WARN_COUNT"
printf 'FAIL: %s\n' "$FAIL_COUNT"

if (( FAIL_COUNT > 0 )); then
  printf '\nNext steps: review failures above, check docker compose ps, inspect API/web logs, confirm disk and backup state, and use the runbook before any remediation.\n'
  exit 1
fi

if (( WARN_COUNT > 0 )); then
  printf '\nNext steps: review warnings above before Domain + HTTPS, risky deploys, or pilot data import.\n'
else
  printf '\nStaging operations health checks completed without warnings or failures.\n'
fi

exit 0
