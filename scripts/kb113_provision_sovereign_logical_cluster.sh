#!/usr/bin/env bash
# KB-113 Step 5: Provision logical dual-node sovereign cluster on Beta appliance.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

APPLIANCE_HOST="${APPLIANCE_SSH_HOST:-192.168.0.226}"
APPLIANCE_USER="${APPLIANCE_SSH_USER:-junexis}"
APPLIANCE_KEY="${APPLIANCE_SSH_KEY:-$ROOT/kevantic-appliance/.tools/build-ssh/kevantic_packer}"

log() { echo "[kb113-provision] $*"; }

log "1/4 Ensure single-node sovereign lab baseline"
bash scripts/kb112_provision_sovereign_beta_lab.sh

log "2/4 Install logical cluster modules on ${APPLIANCE_HOST}"
chmod +x kevantic-appliance/scripts/enable_sovereign_logical_cluster_on_appliance.sh \
  kevantic-appliance/scripts/sovereign_logical_cluster.sh
APPLIANCE_SSH_KEY="$APPLIANCE_KEY" \
  kevantic-appliance/scripts/enable_sovereign_logical_cluster_on_appliance.sh \
  "$APPLIANCE_HOST" "$APPLIANCE_USER"

log "3/4 Pair cluster and start node agents"
ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o BatchMode=yes \
  "${APPLIANCE_USER}@${APPLIANCE_HOST}" \
  'sudo -n sovereign-logical-cluster stop-all || true; sudo -n sovereign-logical-cluster pair; sudo -n sovereign-logical-cluster start-all; sleep 2'

log "4/4 Validate logical HA failover"
bash scripts/kb113_validate_sovereign_ha_failover.sh

log "DONE: Sovereign logical cluster provisioned on ${APPLIANCE_HOST}"
