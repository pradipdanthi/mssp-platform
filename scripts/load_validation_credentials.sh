#!/usr/bin/env bash
# load_validation_credentials.sh — source lab validator passwords from .secrets/validation.env
# Safe to source from validation scripts. Never prints values.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${MSSP_VALIDATION_ENV:-$ROOT/.secrets/validation.env}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  export MSSP_VALIDATION_CREDS_LOADED=1
fi

validation_creds_complete() {
  local v
  for v in PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD \
           CUSTOMER_ADMIN_PASSWORD CUSTOMER_VIEWER_PASSWORD \
           PLATFORM_ADMIN_EMAIL SOC_MANAGER_EMAIL SOC_ANALYST_EMAIL \
           CUSTOMER_ADMIN_EMAIL CUSTOMER_VIEWER_EMAIL \
           CUSTOMER_ADMIN_TENANT CUSTOMER_VIEWER_TENANT; do
    [[ -n "${!v:-}" ]] || return 1
  done
  return 0
}

validation_creds_hint() {
  cat <<EOF
Lab validation passwords are missing.

One-time setup (on VM 100):
  cp /opt/mssp-control/deploy/environments/validation.lab.example.env \\
     /opt/mssp-control/.secrets/validation.env
  chmod 600 /opt/mssp-control/.secrets/validation.env
  # Edit validation.env — fill the five PASSWORD lines with your lab demo user passwords.

Then re-run the validator or post-change checks.
EOF
}
