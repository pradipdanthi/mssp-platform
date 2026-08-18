#!/usr/bin/env bash
# run_post_change_checks.sh — run validators matching files changed since HEAD (or vs base ref).
# Loads lab passwords from .secrets/validation.env — never skips kb011 when creds exist.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_validation_credentials.sh"

BASE="${MSSP_DIFF_BASE:-HEAD}"
if git rev-parse --verify "$BASE" >/dev/null 2>&1; then
  DIFF="$(git diff --name-only "$BASE" 2>/dev/null || true)"
  UNTRACKED="$(git ls-files --others --exclude-standard 2>/dev/null || true)"
  CHANGED="$(printf '%s\n%s' "$DIFF" "$UNTRACKED" | sed '/^$/d' | sort -u)"
else
  CHANGED="$(git status --porcelain | awk '{print $NF}')"
fi

log() { printf '[post_change_checks] %s\n' "$*"; }
die() { log "ERROR: $*"; validation_creds_hint; exit 1; }

run() {
  local script="$1"
  if [[ -x "$script" ]]; then
    log "RUN $script"
    "$script"
  else
    log "SKIP missing $script"
  fi
}

require_kb011_creds() {
  validation_creds_complete || die "kb011 requires all five passwords in .secrets/validation.env"
}

matched=0

if echo "$CHANGED" | grep -qE '^backend-api/|^frontend-admin/|^frontend-customer/'; then
  matched=1
  require_kb011_creds
  run ./scripts/kb011_validate_protected_apis.sh
fi

if echo "$CHANGED" | grep -qE '^frontend-customer/.*(Entitlement|entitlement|navEntitlement)|frontend-customer/src/(App|main|components/Layout)'; then
  matched=1
  run ./scripts/kb_validate_customer_entitlement_nav.sh
fi

if echo "$CHANGED" | grep -qE 'service_catalog|ServiceCatalog'; then
  matched=1
  run ./scripts/kb_validate_admin_service_catalog_ops.sh
fi

if echo "$CHANGED" | grep -qE '^kevantic-appliance/.*(telemetry|forwarder|093[Pp])|^docs/KB093P|^scripts/kb093p'; then
  matched=1
  run ./scripts/kb093p_validate_appliance_critical_alert_forward.sh
fi

if echo "$CHANGED" | grep -qE 'heartbeat|image-release|register_ops|bake_golden_vm199|upgrade_appliance_fleet|upgrade_appliance_heartbeat|^scripts/kb101'; then
  matched=1
  run ./scripts/kb101_validate_golden_fleet_reporting.sh
fi

if echo "$CHANGED" | grep -qE '^deploy/|^docs/KB094|^scripts/production_deploy|^scripts/kb094|^scripts/run_post_change|^scripts/load_validation'; then
  matched=1
  run ./scripts/kb094_validate_production_portability_pack.sh
fi

if echo "$CHANGED" | grep -qE '^backend-api/.*agent_package_builder|^backend-api/.*agent_install_repo|^backend-api/app/endpoint_configs/|^scripts/Enable-MsspWindowsTelemetry|^scripts/bootstrap_windows_telemetry|^scripts/kb088_validate_windows|^scripts/kb105_'; then
  matched=1
  run ./scripts/kb088_validate_windows_telemetry_onboarding.sh
  run ./scripts/kb105_validate_linux_midlayer_edr.sh
fi

if echo "$CHANGED" | grep -qE '^frontend-admin/'; then
  matched=1
  run ./scripts/kb018_validate_admin_frontend_foundation.sh
fi

if [[ "$matched" -eq 0 ]]; then
  log "No mapped validators for changed files — running KB-094 smoke only"
  run ./scripts/kb094_validate_production_portability_pack.sh
fi

log "OK — post-change checks complete"
