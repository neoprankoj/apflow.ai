#!/usr/bin/env bash
set -u

PUBLIC_BASE_URL="${1:-${APFLOW_PUBLIC_BASE_URL:-}}"
HAS_FAILURE=0

section() {
  printf '\n== %s ==\n' "$1"
}

warn() {
  printf 'WARNING: %s\n' "$1"
}

fail() {
  printf 'FAIL: %s\n' "$1"
  HAS_FAILURE=1
}

ok() {
  printf 'OK: %s\n' "$1"
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

curl_status() {
  local url="$1"
  curl -L -sS -o /dev/null --max-time 10 -w '%{http_code}' "$url"
}

check_local_url() {
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
    warn "$label is not reachable at $url. Skipping because the local service may be stopped."
    return 0
  fi

  if [[ "$status" =~ $expected_pattern ]]; then
    ok "$label returned HTTP $status."
  else
    fail "$label returned unexpected HTTP $status from $url."
  fi
}

check_public_api_health() {
  local base_url="$1"
  local status

  if ! command -v curl >/dev/null 2>&1; then
    warn "curl is not installed; skipping public proxy health check."
    return 0
  fi

  status="$(curl_status "$base_url/api/health" 2>/dev/null || true)"
  if [[ -z "$status" || "$status" == "000" ]]; then
    fail "Public proxy API health is not reachable at $base_url/api/health."
    return 0
  fi

  if [[ "$status" =~ ^2[0-9][0-9]$ ]]; then
    ok "Public proxy API health returned HTTP $status."
  else
    fail "Public proxy API health returned HTTP $status from $base_url/api/health."
  fi
}

section "Nginx installation"
if command -v nginx >/dev/null 2>&1; then
  ok "nginx is installed."
  nginx -v 2>&1 || true
else
  warn "nginx is not installed or not on PATH."
fi

section "Nginx config test"
if command -v nginx >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    if sudo nginx -t; then
      ok "sudo nginx -t passed."
    else
      fail "sudo nginx -t failed."
    fi
  else
    warn "passwordless sudo is not available; skipping sudo nginx -t."
  fi
else
  warn "nginx is unavailable; skipping nginx -t."
fi

section "Listening ports 80/443"
if command -v ss >/dev/null 2>&1; then
  if ss -tulpn | grep -E ':(80|443)[[:space:]]' >/dev/null 2>&1; then
    ss -tulpn | grep -E ':(80|443)[[:space:]]' || true
  else
    warn "No listeners found for ports 80 or 443 in ss output."
  fi
elif command -v netstat >/dev/null 2>&1; then
  if netstat -tulpn 2>/dev/null | grep -E ':(80|443)[[:space:]]' >/dev/null 2>&1; then
    netstat -tulpn 2>/dev/null | grep -E ':(80|443)[[:space:]]' || true
  else
    warn "No listeners found for ports 80 or 443 in netstat output."
  fi
else
  warn "Neither ss nor netstat is installed; skipping listening port inspection."
fi

section "Local app checks"
check_local_url "Local web" "http://127.0.0.1:3000" '^[23][0-9][0-9]$'
check_local_url "Local API health" "http://127.0.0.1:8000/health" '^2[0-9][0-9]$'

section "Public proxy check"
if [[ -n "$PUBLIC_BASE_URL" ]]; then
  PUBLIC_BASE_URL="$(sanitize_base_url "$PUBLIC_BASE_URL")"
  printf 'Using public base URL: %s\n' "$PUBLIC_BASE_URL"
  check_public_api_health "$PUBLIC_BASE_URL"
else
  warn "No APFLOW_PUBLIC_BASE_URL or argument provided; skipping public /api/health check."
  warn "Example: bash scripts/check_reverse_proxy.sh http://46.101.97.231"
fi

section "Result"
if [[ "$HAS_FAILURE" -eq 0 ]]; then
  ok "Read-only reverse proxy inspection completed without clear failures."
  exit 0
fi

fail "Reverse proxy inspection found one or more clear failures."
exit 1
