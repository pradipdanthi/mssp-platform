#!/usr/bin/env bash
# Source Sovereign portal lab credentials for validators (never prints secrets).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${SOVEREIGN_PORTAL_LAB_ENV:-$ROOT/.secrets/sovereign_portal_lab.env}"

export SOVEREIGN_PORTAL_LAB_BOOTSTRAP=1

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

# Validator defaults when secrets file absent (lab-only placeholders).
export SOVEREIGN_PORTAL_SOC_USER="${SOVEREIGN_PORTAL_SOC_USER:-soc_engineer}"
export SOVEREIGN_PORTAL_CUSTOMER_USER="${SOVEREIGN_PORTAL_CUSTOMER_USER:-customer_viewer}"
export SOVEREIGN_PORTAL_SOC_ROLE="${SOVEREIGN_PORTAL_SOC_ROLE:-soc_analyst}"
export SOVEREIGN_PORTAL_CUSTOMER_ROLE="${SOVEREIGN_PORTAL_CUSTOMER_ROLE:-customer_viewer}"
export SOVEREIGN_PORTAL_LAB_JWT_SECRET="${SOVEREIGN_PORTAL_LAB_JWT_SECRET:-sovereign-portal-lab-jwt-secret}"

sovereign_portal_login() {
  local user="$1"
  local pass="$2"
  local port="${3:-9443}"
  curl -s --connect-timeout 5 -X POST "http://127.0.0.1:${port}/auth/login" \
    -H 'Content-Type: application/json' \
    -d "$(jq -nc --arg u "$user" --arg p "$pass" '{username:$u,password:$p}')" \
    | jq -r '.access_token // empty'
}

sovereign_portal_auth_header() {
  local token="$1"
  printf 'Authorization: Bearer %s' "$token"
}
