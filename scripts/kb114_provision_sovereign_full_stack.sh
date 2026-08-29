#!/usr/bin/env bash
# KB-114 Step 6: Provision Sovereign Edge full stack on Beta (stub mode on lean hardware).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

APPLIANCE_HOST="${APPLIANCE_SSH_HOST:-192.168.0.226}"
APPLIANCE_USER="${APPLIANCE_SSH_USER:-junexis}"
APPLIANCE_KEY="${APPLIANCE_SSH_KEY:-$ROOT/kevantic-appliance/.tools/build-ssh/kevantic_packer}"
STACK_MODE="${SOVEREIGN_FULL_STACK_MODE:-stub}"

log() { echo "[kb114-provision] $*"; }

log "1/3 Ensure sovereign single-node + logical cluster baseline"
bash scripts/kb113_provision_sovereign_logical_cluster.sh

log "2/3 Install full stack (mode=${STACK_MODE}) on ${APPLIANCE_HOST}"
chmod +x kevantic-appliance/scripts/enable_sovereign_full_stack_on_appliance.sh \
  kevantic-appliance/scripts/sovereign_full_stack.sh \
  kevantic-appliance/scripts/sovereign_full_stack_stub.sh
APPLIANCE_SSH_KEY="$APPLIANCE_KEY" SOVEREIGN_FULL_STACK_MODE="$STACK_MODE" \
  kevantic-appliance/scripts/enable_sovereign_full_stack_on_appliance.sh \
  "$APPLIANCE_HOST" "$APPLIANCE_USER"

log "3/3 Validate sovereign full stack"
bash scripts/kb114_validate_sovereign_full_stack.sh

log "DONE: Sovereign full stack provisioned on ${APPLIANCE_HOST} (mode=${STACK_MODE})"
