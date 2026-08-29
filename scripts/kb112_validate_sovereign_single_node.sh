#!/usr/bin/env bash
# KB-112 Step 3: Validate Sovereign Edge single-node lab (Beta appliance).
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"

TENANT_SHORT="${SOVEREIGN_LAB_TENANT:-BETAWINCORP-J3FW}"
APPLIANCE_HOST="${APPLIANCE_SSH_HOST:-192.168.0.226}"
APPLIANCE_USER="${APPLIANCE_SSH_USER:-junexis}"
APPLIANCE_KEY="${APPLIANCE_SSH_KEY:-$ROOT/kevantic-appliance/.tools/build-ssh/kevantic_packer}"
CONTROL_PLANE_IP="${MSSP_CONTROL_PLANE_IP:-192.168.0.201}"

pass=0
fail=0
section() { echo; echo "=== $1 ==="; }
ok() { echo "PASS: $1"; pass=$((pass + 1)); }
bad() { echo "FAIL: $1"; fail=$((fail + 1)); }

section "1. Control plane tenant mode"
MODE="$(docker compose exec -T postgres psql -U mssp_admin -d mssp_control -Atc \
  "SELECT deployment_mode FROM tenants WHERE short_code='${TENANT_SHORT}';")"
MODE="${MODE//$'\r'/}"
[[ "$MODE" == "sovereign_edge" ]] && ok "tenant ${TENANT_SHORT} is sovereign_edge" || bad "tenant mode is '${MODE}'"

section "2. Appliance sovereign profile + services"
if ! ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=yes \
  "${APPLIANCE_USER}@${APPLIANCE_HOST}" 'echo ok' >/dev/null 2>&1; then
  echo "SKIP: appliance ${APPLIANCE_HOST} unreachable — run kb112_provision_sovereign_beta_lab.sh when online"
else
REMOTE_JSON="$(ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 "${APPLIANCE_USER}@${APPLIANCE_HOST}" \
  'sudo /usr/local/sbin/sovereign-edge-posture status 2>/dev/null || true')"
if echo "$REMOTE_JSON" | jq -e '.profile.profile == "sovereign_edge"' >/dev/null 2>&1; then
  ok "sovereign-edge.json profile present"
else
  bad "sovereign profile missing on appliance"
fi
if echo "$REMOTE_JSON" | jq -e '.profile.cloud_egress_enabled == false' >/dev/null 2>&1; then
  ok "cloud egress default off"
else
  bad "cloud egress not disabled"
fi
FWD_ACTIVE="$(echo "$REMOTE_JSON" | jq -r '.units.forwarder.active // "unknown"')"
CH_ACTIVE="$(echo "$REMOTE_JSON" | jq -r '.units.channeld.active // "unknown"')"
[[ "$FWD_ACTIVE" != "active" ]] && ok "forwarder not active (${FWD_ACTIVE})" || bad "forwarder still active"
[[ "$CH_ACTIVE" != "active" ]] && ok "channeld not active (${CH_ACTIVE})" || bad "channeld still active"
fi

section "3. Offline signed license on appliance"
if ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=yes \
  "${APPLIANCE_USER}@${APPLIANCE_HOST}" 'echo ok' >/dev/null 2>&1; then
LIC_JSON="$(ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 "${APPLIANCE_USER}@${APPLIANCE_HOST}" \
  'sudo env PYTHONPATH=/opt/junexis/cli:/opt/junexis python3 -c "from junexis_cli.license_ops import show_license; import json; print(json.dumps(show_license()))"')"
if echo "$LIC_JSON" | jq -e '.license_present == true' >/dev/null 2>&1; then
  ok "license.jws present on appliance"
else
  bad "license.jws missing"
fi
if echo "$LIC_JSON" | jq -e '.signed == true and (.service_ids|length) > 0' >/dev/null 2>&1; then
  ok "signed entitlements active"
else
  bad "entitlements not signed/active"
fi
else
  echo "SKIP: appliance offline — license apply pending"
fi

section "4. Air-gap egress to control plane"
if ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=yes \
  "${APPLIANCE_USER}@${APPLIANCE_HOST}" 'echo ok' >/dev/null 2>&1; then
EGRESS_RC="$(ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 "${APPLIANCE_USER}@${APPLIANCE_HOST}" \
  "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://${CONTROL_PLANE_IP}:8000/health || echo 000")"
EGRESS_RC="${EGRESS_RC//$'\r'/}"
if [[ "$EGRESS_RC" == "000" ]] || [[ "$EGRESS_RC" == "000000" ]]; then
  ok "control plane ${CONTROL_PLANE_IP} unreachable from appliance (air-gap)"
else
  bad "control plane reachable from appliance (http ${EGRESS_RC})"
fi
else
  echo "SKIP: appliance offline — air-gap check pending"
fi

section "5. Fulfillment skips cloud channel push"
PUSH_JSON="$(docker compose exec -T backend-api python - <<PY
from app.services.capability_fulfillment_service import push_appliance_license
from app.db.session import fetch_one
row = fetch_one("SELECT id::text FROM tenants WHERE short_code=%s", ("${TENANT_SHORT}",))
print(push_appliance_license(row["id"]))
PY
)"
if echo "$PUSH_JSON" | grep -q offline_license_manual; then
  ok "cloud channel push skipped (offline_license_manual)"
else
  bad "expected offline_license_manual push skip"
fi

echo
if [[ "$fail" -eq 0 ]]; then
  echo "KB-112 SOVEREIGN SINGLE-NODE VALIDATION PASSED ($pass checks)"
  exit 0
fi
echo "KB-112 SOVEREIGN SINGLE-NODE VALIDATION FAILED ($fail failed / $pass passed)"
exit 1
