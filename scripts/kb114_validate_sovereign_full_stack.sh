#!/usr/bin/env bash
# KB-114 Step 6: Validate Sovereign Edge full stack (TheHive, Shuffle stubs, unified portal).
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"

APPLIANCE_HOST="${APPLIANCE_SSH_HOST:-192.168.0.226}"
APPLIANCE_USER="${APPLIANCE_SSH_USER:-junexis}"
APPLIANCE_KEY="${APPLIANCE_SSH_KEY:-$ROOT/kevantic-appliance/.tools/build-ssh/kevantic_packer}"
PORTAL_PORT="${SOVEREIGN_PORTAL_PORT:-9443}"
LAB_ENV="${SOVEREIGN_PORTAL_LAB_ENV:-$ROOT/.secrets/sovereign_portal_lab.env}"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_sovereign_portal_lab_credentials.sh"

pass=0
fail=0
section() { echo; echo "=== $1 ==="; }
ok() { echo "PASS: $1"; pass=$((pass + 1)); }
bad() { echo "FAIL: $1"; fail=$((fail + 1)); }

remote() {
  ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes \
    "${APPLIANCE_USER}@${APPLIANCE_HOST}" "$@"
}

remote_portal_login() {
  local user="$1"
  local pass="$2"
  local payload
  payload="$(jq -nc --arg u "$user" --arg p "$pass" '{username:$u,password:$p}')"
  remote "curl -s --connect-timeout 5 -X POST http://127.0.0.1:${PORTAL_PORT}/auth/login \
    -H 'Content-Type: application/json' \
    -d $(printf '%q' "$payload")"
}

section "0. Appliance reachability"
if ! remote 'echo ok' >/dev/null 2>&1; then
  echo "FAIL: appliance ${APPLIANCE_HOST} unreachable"
  exit 1
fi
ok "appliance reachable"

section "0b. Portal lab auth provisioning"
if [[ -f "$LAB_ENV" ]]; then
  scp -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no "$LAB_ENV" \
    "${APPLIANCE_USER}@${APPLIANCE_HOST}:/tmp/sovereign-portal-lab.env" >/dev/null
  remote "sudo -n install -d -m 0750 /etc/junexis && sudo -n install -m 0640 /tmp/sovereign-portal-lab.env /etc/junexis/sovereign-portal-lab.env && rm -f /tmp/sovereign-portal-lab.env"
  remote "sudo -n sovereign-full-stack stop-portal >/dev/null 2>&1 || true; sudo -n env SOVEREIGN_FULL_STACK_MODE=stub sovereign-full-stack enable >/dev/null"
  sleep 2
  ok "portal lab env installed and restarted"
else
  bad "missing lab env file ${LAB_ENV}"
fi

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

section "4. Portal authentication + RBAC matrix"
SOC_TOKEN="$(remote_portal_login "$SOVEREIGN_PORTAL_SOC_USER" "$SOVEREIGN_PORTAL_SOC_PASSWORD" | jq -r '.access_token // empty')"
CUST_TOKEN="$(remote_portal_login "$SOVEREIGN_PORTAL_CUSTOMER_USER" "$SOVEREIGN_PORTAL_CUSTOMER_PASSWORD" | jq -r '.access_token // empty')"
[[ -n "$SOC_TOKEN" ]] && ok "SOC login issued bearer token" || bad "SOC login failed"
[[ -n "$CUST_TOKEN" ]] && ok "customer login issued bearer token" || bad "customer login failed"

SPOOF_CODE="$(remote "curl -s -o /dev/null -w '%{http_code}' -H 'X-Sovereign-Role: soc_analyst' http://127.0.0.1:${PORTAL_PORT}/admin/tenants")"
[[ "$SPOOF_CODE" == "401" ]] && ok "X-Sovereign-Role spoof denied (401)" || bad "header spoof got ${SPOOF_CODE}"

SOC_CODE="$(remote "curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer ${SOC_TOKEN}' http://127.0.0.1:${PORTAL_PORT}/admin/tenants")"
CUST_ADMIN_CODE="$(remote "curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer ${CUST_TOKEN}' http://127.0.0.1:${PORTAL_PORT}/admin/tenants")"
CUST_INC_CODE="$(remote "curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer ${CUST_TOKEN}' http://127.0.0.1:${PORTAL_PORT}/api/v1/customer/incidents")"
ANON_CODE="$(remote "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:${PORTAL_PORT}/admin/tenants")"
[[ "$SOC_CODE" == "200" ]] && ok "SOC engineer /admin/tenants 200" || bad "SOC /admin/tenants got ${SOC_CODE}"
[[ "$CUST_ADMIN_CODE" == "403" ]] && ok "customer blocked from /admin 403" || bad "customer /admin got ${CUST_ADMIN_CODE}"
[[ "$CUST_INC_CODE" == "200" ]] && ok "customer incidents 200" || bad "customer incidents got ${CUST_INC_CODE}"
[[ "$ANON_CODE" == "401" ]] && ok "anonymous /admin denied 401" || bad "anonymous /admin got ${ANON_CODE}"

section "5. Local proxy routes (SOC only)"
PROXY_SOC="$(remote "curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer ${SOC_TOKEN}' http://127.0.0.1:${PORTAL_PORT}/proxy/thehive/")"
PROXY_CUST="$(remote "curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer ${CUST_TOKEN}' http://127.0.0.1:${PORTAL_PORT}/proxy/thehive/")"
[[ "$PROXY_SOC" == "200" ]] && ok "SOC TheHive proxy 200" || bad "SOC TheHive proxy ${PROXY_SOC}"
[[ "$PROXY_CUST" == "403" ]] && ok "customer TheHive proxy blocked 403" || bad "customer proxy ${PROXY_CUST}"

section "6. Unit tests (CI parity)"
if docker compose exec -T backend-api python -m unittest tests.test_sovereign_full_stack tests.test_sovereign_portal_auth -q 2>/dev/null; then
  ok "sovereign full stack + portal auth tests (container)"
elif (cd backend-api && PYTHONPATH="$ROOT/kevantic-appliance" python3 -m unittest tests.test_sovereign_full_stack tests.test_sovereign_portal_auth -q 2>/dev/null); then
  ok "sovereign full stack + portal auth tests (host)"
else
  bad "sovereign unit tests"
fi

echo
if [[ "$fail" -eq 0 ]]; then
  echo "KB-114 SOVEREIGN FULL-STACK VALIDATION PASSED ($pass checks)"
  exit 0
fi
echo "KB-114 SOVEREIGN FULL-STACK VALIDATION FAILED ($fail failed / $pass passed)"
exit 1
