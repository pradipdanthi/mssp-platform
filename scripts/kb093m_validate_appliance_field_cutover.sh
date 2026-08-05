#!/usr/bin/env bash
# KB-093M Track 5 — field cutover validators (static + live smoke on VM 114)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MGMT_IP="${JUNEXIS_MGMT_VM_IP:-192.168.0.224}"
MGMT="http://${MGMT_IP}:8000"
CP="http://127.0.0.1:8000"
BODY="$(mktemp)"
FAKE_NAME="kb093m-field-cutover-appliance"
FAKE_SITE="KB093M Field Cutover Site (safe to delete)"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; rm -f "$BODY"; exit 1; }
cleanup() {
  rm -f "$BODY"
  if [[ -n "${CLEAN_SQL:-}" ]]; then
    docker compose exec -T postgres psql -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
      -c "DELETE FROM appliances WHERE appliance_name = '${FAKE_NAME}';" >/dev/null 2>&1 || true
    docker compose exec -T postgres psql -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
      -c "DELETE FROM appliance_activation_tokens WHERE site_name = '${FAKE_SITE}';" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "== KB-093M Appliance field cutover =="

test -f docs/KB093M_APPLIANCE_FIELD_CUTOVER.md || fail "missing KB093M doc"
pass "KB093M doc present"

grep -q 'applianceRegisterCommand' frontend-admin/src/pages/AppliancesPage.tsx \
  || fail "Admin missing Copy register command"
grep -q '192.168.0.224:8000' junexis-appliance/ansible/group_vars/all.yml \
  || fail "ISO defaults not on VM114"
pass "operator register path baked into Admin + ISO defaults"

curl -fsS "${MGMT}/health" | grep -q '"api":"ok"' || fail "VM114 health"
code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "${MGMT}/appliance/register" \
  -H 'Content-Type: application/json' \
  -d '{"activation_token":"not-a-real-token","appliance_name":"kb093m-garbage"}')
[[ "$code" == "401" ]] || fail "VM114 register garbage token expected 401 got $code"
pass "VM114 /appliance/register reachable (401 on bad token)"

# Optional full register when PLATFORM_ADMIN_PASSWORD is set (non-interactive CI/lab).
if [[ -n "${PLATFORM_ADMIN_PASSWORD:-}" ]]; then
  CLEAN_SQL=1
  token=$(curl -fsS -X POST "${CP}/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"${PLATFORM_ADMIN_EMAIL:-platform.admin@example.local}\",\"password\":\"${PLATFORM_ADMIN_PASSWORD}\"}" \
    | jq -r .access_token)
  [[ -n "$token" && "$token" != "null" ]] || fail "admin login"
  unset PLATFORM_ADMIN_PASSWORD
  tenant=$(curl -fsS -H "Authorization: Bearer $token" "${CP}/admin/tenants" \
    | jq -r '.tenants[] | select(.short_code=="DEMO") | .id')
  [[ -n "$tenant" && "$tenant" != "null" ]] || fail "DEMO tenant"
  curl -fsS -o "$BODY" -X POST \
    -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
    -d "$(jq -n --arg s "$FAKE_SITE" '{site_name:$s, expires_in_hours:2}')" \
    "${CP}/admin/tenants/${tenant}/appliance-activation-tokens"
  raw=$(jq -r .token "$BODY")
  [[ -n "$raw" && "$raw" != "null" ]] || fail "activation token create"
  curl -fsS -o "$BODY" -X POST "${MGMT}/appliance/register" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --arg t "$raw" --arg n "$FAKE_NAME" \
      '{activation_token:$t, appliance_name:$n, agent_version:"kb093m-1.0"}')"
  jq -e '.status == "registered"' "$BODY" >/dev/null || fail "register on VM114"
  jq -e '.appliance_api_key | type == "string" and length > 10' "$BODY" >/dev/null || fail "api key returned"
  pass "5.1 live register against VM114 succeeded"
else
  echo "SKIP: full register (set PLATFORM_ADMIN_PASSWORD to exercise 5.1 live)"
fi

echo "KB093M_VALIDATE_PASS"
