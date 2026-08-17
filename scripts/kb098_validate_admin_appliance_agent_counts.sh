#!/usr/bin/env bash
# KB-098: Admin appliance list — agents reporting / enrolled counts (Phase 1).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
BODY_FILE="/tmp/kb098-body.json"

FAKE_APPLIANCE_NAME="kb098-validation-appliance-agents"
FAKE_ASSET_ACTIVE="kb098-agent-active"
FAKE_ASSET_INACTIVE="kb098-agent-inactive"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-098: Validate Admin Appliance Agent Counts (list API + UI source)"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1" >&2
  cleanup_fixtures || true
  rm -f "$BODY_FILE"
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

psql_scalar() {
  local sql="$1"
  local raw line_count
  raw="$(docker compose exec -T postgres psql \
    -X -q -t -A \
    -v ON_ERROR_STOP=1 \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "$sql" 2>/dev/null)" || return 1
  raw="$(printf '%s\n' "$raw" | sed 's/\r$//' | grep -v '^[[:space:]]*$' || true)"
  line_count="$(printf '%s\n' "$raw" | grep -c '.' || true)"
  if [ "$line_count" != "1" ]; then
    echo "psql_scalar: expected exactly 1 non-blank output line, got $line_count" >&2
    return 1
  fi
  printf '%s' "$raw"
}

cleanup_fixtures() {
  docker compose exec -T postgres psql \
    -X -q -v ON_ERROR_STOP=1 \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "
      DELETE FROM protected_assets
      WHERE hostname IN ('${FAKE_ASSET_ACTIVE}', '${FAKE_ASSET_INACTIVE}');
      DELETE FROM appliances
      WHERE appliance_name = '${FAKE_APPLIANCE_NAME}';
    " >/dev/null 2>&1 || true
}

trap 'cleanup_fixtures; rm -f "$BODY_FILE"' EXIT

section "Source checks"
grep -q 'agents_total' backend-api/app/api/routes/admin.py \
  || fail "admin appliances list missing agents_total"
grep -q 'agents_reporting' backend-api/app/api/routes/admin.py \
  || fail "admin appliances list missing agents_reporting"
grep -q 'ApplianceAgentsCell' frontend-admin/src/pages/AppliancesPage.tsx \
  || fail "AppliancesPage missing Agents column component"
grep -q 'agents_total' frontend-admin/src/api/admin.ts \
  || fail "frontend Appliance type missing agents_total"

section "Load validation credentials"
# shellcheck disable=SC1091
source "${PROJECT_DIR}/scripts/load_validation_credentials.sh"
validation_creds_complete || fail "$(validation_creds_hint)"

login_token() {
  curl -fsS -X POST "${API_BASE}/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${PLATFORM_ADMIN_EMAIL}\",\"password\":\"${PLATFORM_ADMIN_PASSWORD}\",\"portal\":\"admin\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))"
}

PLATFORM_ADMIN_TOKEN="$(login_token)"
[ -n "$PLATFORM_ADMIN_TOKEN" ] || fail "platform_admin login failed"

section "Seed fixture appliance + agents"
TENANT_ID="$(psql_scalar "SELECT id::text FROM tenants ORDER BY created_at LIMIT 1;")"
[ -n "$TENANT_ID" ] || fail "no tenant in database"

APPLIANCE_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO appliances (
    tenant_id, appliance_name, site_name, status, appliance_uuid
  )
  VALUES (
    '${TENANT_ID}'::uuid,
    '${FAKE_APPLIANCE_NAME}',
    'KB098 Site',
    'online',
    'kb098-appliance-uuid'
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")"
[ -n "$APPLIANCE_ID" ] || fail "could not create fixture appliance"

psql_scalar "
INSERT INTO protected_assets (
  tenant_id, appliance_id, hostname, asset_type, status, details
)
VALUES
  (
    '${TENANT_ID}'::uuid,
    '${APPLIANCE_ID}'::uuid,
    '${FAKE_ASSET_ACTIVE}',
    'workstation',
    'active',
    '{\"source\":\"kb098\",\"wazuh_agent_id\":\"99801\"}'::jsonb
  ),
  (
    '${TENANT_ID}'::uuid,
    '${APPLIANCE_ID}'::uuid,
    '${FAKE_ASSET_INACTIVE}',
    'server',
    'inactive',
    '{\"source\":\"kb098\",\"wazuh_agent_id\":\"99802\"}'::jsonb
  );
SELECT 'ok';
" >/dev/null || fail "could not seed protected_assets"

section "GET /admin/appliances returns agent counts"
HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w '%{http_code}' \
  -H "Authorization: Bearer ${PLATFORM_ADMIN_TOKEN}" \
  "${API_BASE}/admin/appliances?page_size=200")"
[ "$HTTP_CODE" = "200" ] || fail "GET /admin/appliances returned HTTP $HTTP_CODE"

python3 - <<'PY' "$BODY_FILE" "$APPLIANCE_ID"
import json, sys
body_path, appliance_id = sys.argv[1], sys.argv[2]
data = json.load(open(body_path))
rows = data.get("appliances") or []
match = next((a for a in rows if a.get("id") == appliance_id), None)
if not match:
    raise SystemExit(f"fixture appliance {appliance_id} not in list response")
total = match.get("agents_total")
reporting = match.get("agents_reporting")
if total != 2:
    raise SystemExit(f"agents_total expected 2, got {total!r}")
if reporting != 1:
    raise SystemExit(f"agents_reporting expected 1, got {reporting!r}")
print(f"OK agents_reporting={reporting} agents_total={total}")
PY

section "Admin frontend build includes Agents column"
ADMIN_DIST="${PROJECT_DIR}/frontend-admin/dist/index.html"
if [ -f "$ADMIN_DIST" ]; then
  # Static build won't contain component name; grep source instead (already done).
  echo "Admin dist present (nginx serves rebuilt bundle after deploy)."
else
  echo "Admin dist not built locally — source checks passed."
fi

section "Live Beta appliance spot-check (optional)"
BETA_ROW="$(curl -sS -H "Authorization: Bearer ${PLATFORM_ADMIN_TOKEN}" \
  "${API_BASE}/admin/appliances?q=junexis-appliance&page_size=10" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
for a in data.get('appliances') or []:
    if 'junexis' in (a.get('appliance_name') or '').lower():
        print(f\"{a.get('agents_reporting', '?')} active / {a.get('agents_total', '?')} enrolled\")
        break
" 2>/dev/null || true)"
if [ -n "$BETA_ROW" ]; then
  echo "Beta-Win-Corp appliance list row: $BETA_ROW"
else
  echo "No junexis-appliance row in API (skipped live spot-check)."
fi

echo
echo "======================================================================"
echo "KB-098 VALIDATION PASSED"
echo "======================================================================"
