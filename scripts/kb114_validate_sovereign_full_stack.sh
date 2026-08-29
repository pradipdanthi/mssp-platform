#!/usr/bin/env bash
# KB-114 Step 6: Validate Sovereign Edge full stack (TheHive, Shuffle stubs, unified portal).
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"

APPLIANCE_HOST="${APPLIANCE_SSH_HOST:-192.168.0.226}"
APPLIANCE_USER="${APPLIANCE_SSH_USER:-junexis}"
APPLIANCE_KEY="${APPLIANCE_SSH_KEY:-$ROOT/kevantic-appliance/.tools/build-ssh/kevantic_packer}"
PORTAL_PORT="${SOVEREIGN_PORTAL_PORT:-9443}"

pass=0
fail=0
section() { echo; echo "=== $1 ==="; }
ok() { echo "PASS: $1"; pass=$((pass + 1)); }
bad() { echo "FAIL: $1"; fail=$((fail + 1)); }

remote() {
  ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes \
    "${APPLIANCE_USER}@${APPLIANCE_HOST}" "$@"
}

section "0. Appliance reachability"
if ! remote 'echo ok' >/dev/null 2>&1; then
  echo "FAIL: appliance ${APPLIANCE_HOST} unreachable"
  exit 1
fi
ok "appliance reachable"

section "1. Full stack manifest + compose staged"
STATUS_JSON="$(remote 'sudo -n sovereign-full-stack status')"
echo "$STATUS_JSON" | jq -e '.manifest.profile == "sovereign_full_stack"' >/dev/null 2>&1 \
  && ok "sovereign_full_stack manifest" || bad "manifest missing"
echo "$STATUS_JSON" | jq -e '.compose_installed == true' >/dev/null 2>&1 \
  && ok "compose files installed" || bad "compose files missing"
echo "$STATUS_JSON" | jq -e '.install_marker == true' >/dev/null 2>&1 \
  && ok "install marker present" || bad "install marker missing"

section "2. TheHive + Shuffle endpoints (stub or docker)"
TH_OPEN="$(echo "$STATUS_JSON" | jq -r '.ports.thehive.open')"
SH_OPEN="$(echo "$STATUS_JSON" | jq -r '.ports.shuffle.open')"
[[ "$TH_OPEN" == "true" ]] && ok "TheHive port open" || bad "TheHive port closed"
[[ "$SH_OPEN" == "true" ]] && ok "Shuffle port open" || bad "Shuffle port closed"

section "3. Unified portal health"
PORTAL_OPEN="$(echo "$STATUS_JSON" | jq -r '.ports.unified_portal.open')"
[[ "$PORTAL_OPEN" == "true" ]] && ok "unified portal port open" || bad "unified portal port closed"
HEALTH="$(remote "curl -s --connect-timeout 3 http://127.0.0.1:${PORTAL_PORT}/health")"
echo "$HEALTH" | jq -e '.ok == true' >/dev/null 2>&1 && ok "portal /health" || bad "portal /health"

section "4. RBAC matrix on unified portal"
SOC_CODE="$(remote "curl -s -o /dev/null -w '%{http_code}' -H 'X-Sovereign-Role: soc_analyst' http://127.0.0.1:${PORTAL_PORT}/admin/tenants")"
CUST_ADMIN_CODE="$(remote "curl -s -o /dev/null -w '%{http_code}' -H 'X-Sovereign-Role: customer_admin' http://127.0.0.1:${PORTAL_PORT}/admin/tenants")"
CUST_INC_CODE="$(remote "curl -s -o /dev/null -w '%{http_code}' -H 'X-Sovereign-Role: customer_viewer' http://127.0.0.1:${PORTAL_PORT}/api/v1/customer/incidents")"
[[ "$SOC_CODE" == "200" ]] && ok "SOC engineer /admin/tenants 200" || bad "SOC /admin/tenants got ${SOC_CODE}"
[[ "$CUST_ADMIN_CODE" == "403" ]] && ok "customer blocked from /admin 403" || bad "customer /admin got ${CUST_ADMIN_CODE}"
[[ "$CUST_INC_CODE" == "200" ]] && ok "customer incidents 200" || bad "customer incidents got ${CUST_INC_CODE}"

section "5. Local proxy routes (SOC only)"
PROXY_SOC="$(remote "curl -s -o /dev/null -w '%{http_code}' -H 'X-Sovereign-Role: soc_analyst' http://127.0.0.1:${PORTAL_PORT}/proxy/thehive/")"
PROXY_CUST="$(remote "curl -s -o /dev/null -w '%{http_code}' -H 'X-Sovereign-Role: customer_viewer' http://127.0.0.1:${PORTAL_PORT}/proxy/thehive/")"
[[ "$PROXY_SOC" == "200" ]] && ok "SOC TheHive proxy 200" || bad "SOC TheHive proxy ${PROXY_SOC}"
[[ "$PROXY_CUST" == "403" ]] && ok "customer TheHive proxy blocked 403" || bad "customer proxy ${PROXY_CUST}"

section "6. Unit tests (CI parity)"
if docker compose exec -T backend-api python -m unittest tests.test_sovereign_full_stack -q 2>/dev/null; then
  ok "test_sovereign_full_stack (container)"
elif (cd backend-api && python3 -m unittest tests.test_sovereign_full_stack -q 2>/dev/null); then
  ok "test_sovereign_full_stack (host)"
else
  bad "test_sovereign_full_stack"
fi

echo
if [[ "$fail" -eq 0 ]]; then
  echo "KB-114 SOVEREIGN FULL-STACK VALIDATION PASSED ($pass checks)"
  exit 0
fi
echo "KB-114 SOVEREIGN FULL-STACK VALIDATION FAILED ($fail failed / $pass passed)"
exit 1
