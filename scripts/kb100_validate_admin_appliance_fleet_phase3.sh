#!/usr/bin/env bash
# KB-100: Admin appliance fleet Phase 3 — seats, jobs, detail page.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3000"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-100: Validate Admin Appliance Fleet Phase 3"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1" >&2
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

section "Source checks"
grep -q 'licensed_endpoints' backend-api/app/api/routes/admin.py \
  || fail "admin appliances list missing licensed_endpoints"
grep -q 'pending_jobs_count' backend-api/app/api/routes/admin.py \
  || fail "admin appliances list missing pending_jobs_count"
grep -q 'ApplianceDetailPage' frontend-admin/src/App.tsx \
  || fail "App.tsx missing ApplianceDetailPage route"
grep -q 'getApplianceDetail' frontend-admin/src/api/admin.ts \
  || fail "admin.ts missing getApplianceDetail"
grep -q 'ApplianceSeatsCell' frontend-admin/src/pages/AppliancesPage.tsx \
  || fail "AppliancesPage missing Seats column"
grep -q '_collect_resource_metrics' kevantic-appliance/cli/kevantic-cli/kevantic_cli/register_ops.py \
  || fail "appliance heartbeat missing resource metrics collector"

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

section "GET /admin/appliances includes Phase 3 list fields"
LIST="$(curl -fsS -H "Authorization: Bearer ${PLATFORM_ADMIN_TOKEN}" \
  "${API_BASE}/admin/appliances?page_size=5")"
python3 - <<'PY' "$LIST"
import json, sys
data = json.loads(sys.argv[1])
rows = data.get("appliances") or []
if not rows:
    print("OK no appliances in lab (list shape not checked)")
    raise SystemExit(0)
row = rows[0]
for key in ("licensed_endpoints", "pending_jobs_count", "failed_jobs_count", "enabled_services"):
    if key not in row:
        raise SystemExit(f"missing list field {key}")
print("OK list fields:", {k: row.get(k) for k in ("licensed_endpoints", "pending_jobs_count", "failed_jobs_count")})
PY

section "GET /admin/appliances/{id} detail"
APPLIANCE_ID="$(python3 - <<'PY' "$LIST"
import json, sys
rows = json.loads(sys.argv[1]).get("appliances") or []
print(rows[0]["id"] if rows else "")
PY
)"
if [ -n "$APPLIANCE_ID" ]; then
  DETAIL_CODE="$(curl -sS -o /tmp/kb100-detail.json -w '%{http_code}' \
    -H "Authorization: Bearer ${PLATFORM_ADMIN_TOKEN}" \
    "${API_BASE}/admin/appliances/${APPLIANCE_ID}")"
  [ "$DETAIL_CODE" = "200" ] || fail "detail HTTP $DETAIL_CODE"
  python3 - <<'PY'
import json
d = json.load(open("/tmp/kb100-detail.json"))
for key in ("pending_jobs_count", "failed_jobs_count", "protected_assets", "enabled_services"):
    if key not in d:
        raise SystemExit(f"detail missing {key}")
print("OK detail fields present")
PY
fi

section "Admin frontend serves appliances route"
HOME_CODE="$(curl -sS -o /dev/null -w '%{http_code}' "${FRONTEND_BASE}/appliances")"
[ "$HOME_CODE" = "200" ] || fail "GET /appliances returned HTTP $HOME_CODE"

echo
echo "======================================================================"
echo "KB-100 VALIDATION PASSED"
echo "======================================================================"
