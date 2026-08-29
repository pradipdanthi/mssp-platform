#!/usr/bin/env bash
# KB-112 Step 3: Provision Sovereign Edge single-node lab on Beta appliance.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TENANT_SHORT="${SOVEREIGN_LAB_TENANT:-BETAWINCORP-J3FW}"
APPLIANCE_HOST="${APPLIANCE_SSH_HOST:-192.168.0.226}"
APPLIANCE_USER="${APPLIANCE_SSH_USER:-junexis}"
APPLIANCE_KEY="${APPLIANCE_SSH_KEY:-$ROOT/kevantic-appliance/.tools/build-ssh/kevantic_packer}"
LICENSE_OUT="${SOVEREIGN_LICENSE_OUT:-/tmp/sovereign-${TENANT_SHORT}.jws}"
SKIP_APPLIANCE=0

log() { echo "[kb112-provision] $*"; }

log "1/5 Set tenant ${TENANT_SHORT} deployment_mode=sovereign_edge"
docker compose exec -T postgres psql -U mssp_admin -d mssp_control -v ON_ERROR_STOP=1 -c \
  "UPDATE tenants SET deployment_mode = 'sovereign_edge' WHERE short_code = '${TENANT_SHORT}';"

log "2/5 Enable sovereign profile on ${APPLIANCE_HOST}"
if ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=yes \
  "${APPLIANCE_USER}@${APPLIANCE_HOST}" 'echo ok' >/dev/null 2>&1; then
  chmod +x kevantic-appliance/scripts/enable_sovereign_edge_profile_on_appliance.sh \
    kevantic-appliance/scripts/sovereign_edge_posture.sh
  APPLIANCE_SSH_KEY="$APPLIANCE_KEY" \
    kevantic-appliance/scripts/enable_sovereign_edge_profile_on_appliance.sh \
    "$APPLIANCE_HOST" "$APPLIANCE_USER"
else
  log "WARN: appliance ${APPLIANCE_HOST} unreachable — skipping steps 2 and 4"
  SKIP_APPLIANCE=1
fi

log "3/5 Export offline license JWS from control plane"
docker compose cp scripts/export_sovereign_offline_license.py backend-api:/tmp/export_sovereign_offline_license.py
docker compose exec -T backend-api python /tmp/export_sovereign_offline_license.py \
  --tenant-short-code "$TENANT_SHORT" \
  --output "/tmp/sovereign-${TENANT_SHORT}.jws" | tee /tmp/sovereign-export-meta.json
docker compose cp "backend-api:/tmp/sovereign-${TENANT_SHORT}.jws" "$LICENSE_OUT"

if [[ "$SKIP_APPLIANCE" != "1" ]]; then
  log "4/5 Apply offline license on appliance (field engineer simulation)"
  scp -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no \
    "$LICENSE_OUT" "${APPLIANCE_USER}@${APPLIANCE_HOST}:/tmp/sovereign-license.jws"
  ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no "${APPLIANCE_USER}@${APPLIANCE_HOST}" \
    'sudo env PYTHONPATH=/opt/junexis/cli:/opt/junexis python3 - <<"PY"
from pathlib import Path
from junexis_cli.license_ops import apply_license_file
import json
print(json.dumps(apply_license_file(Path("/tmp/sovereign-license.jws")), indent=2))
PY'
else
  log "SKIP 4/5: license exported to ${LICENSE_OUT} — apply on appliance when online"
fi

log "5/5 Validate single-node sovereign lab"
bash scripts/kb112_validate_sovereign_single_node.sh

log "DONE: Sovereign Edge lab provisioned for ${TENANT_SHORT} (appliance skip=${SKIP_APPLIANCE})"
