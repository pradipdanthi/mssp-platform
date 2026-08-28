#!/usr/bin/env bash
# KB-099: Admin appliance fleet visibility Phase 2 — heartbeat age, version, resources, services.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
BODY_FILE="/tmp/kb099-body.json"

FAKE_APPLIANCE_NAME="kb099-validation-appliance-fleet"
FAKE_ASSET_ACTIVE="kb099-agent-active"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-099: Validate Admin Appliance Fleet Visibility (Phase 2)"
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
      DELETE FROM appliance_heartbeats
      WHERE appliance_id IN (
        SELECT id FROM appliances WHERE appliance_name = '${FAKE_APPLIANCE_NAME}'
      );
      DELETE FROM protected_assets WHERE hostname = '${FAKE_ASSET_ACTIVE}';
      DELETE FROM appliances WHERE appliance_name = '${FAKE_APPLIANCE_NAME}';
    " >/dev/null 2>&1 || true
}

trap 'cleanup_fixtures; rm -f "$BODY_FILE"' EXIT

section "Source checks"
grep -q 'git_commit' backend-api/app/api/routes/admin.py \
  || fail "admin appliances list missing git_commit"
grep -q 'ApplianceHeartbeatCell' frontend-admin/src/components/appliance/ApplianceFleetCells.tsx \
  || fail "missing ApplianceHeartbeatCell"
grep -q 'ApplianceHealthCell' frontend-admin/src/components/appliance/ApplianceFleetCells.tsx \
  || fail "missing ApplianceHealthCell"
grep -q 'ApplianceServicesCell' frontend-admin/src/components/appliance/ApplianceFleetCells.tsx \
  || fail "missing ApplianceServicesCell"
grep -q 'formatRelativeHeartbeat' frontend-admin/src/utils/applianceFleet.ts \
  || fail "missing formatRelativeHeartbeat utility"

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

section "Seed fixture appliance + heartbeat + services"
TENANT_ID="$(psql_scalar "SELECT id::text FROM tenants ORDER BY created_at LIMIT 1;")"
[ -n "$TENANT_ID" ] || fail "no tenant in database"

APPLIANCE_ID="$(psql_scalar "
WITH inserted AS (
  INSERT INTO appliances (
    tenant_id, appliance_name, site_name, status, appliance_uuid,
    config_version, git_commit, enabled_services, last_seen_at
  )
  VALUES (
    '${TENANT_ID}'::uuid,
    '${FAKE_APPLIANCE_NAME}',
    'KB099 Site',
    'online',
    'kb099-appliance-uuid',
    'cfg-1.2.3',
    'abc123def456',
    ARRAY['svc-01','svc-06']::text[],
    NOW()
  )
  RETURNING id
)
SELECT id::text FROM inserted;
")"
[ -n "$APPLIANCE_ID" ] || fail "could not create fixture appliance"

psql_scalar "
INSERT INTO appliance_heartbeats (
  appliance_id, health_status, cpu_percent, memory_percent, disk_percent
)
VALUES (
  '${APPLIANCE_ID}'::uuid,
  'healthy',
  12.5,
  48.0,
  71.0
);
SELECT 'ok';
" >/dev/null || fail "could not seed appliance heartbeat"

section "GET /admin/appliances returns Phase 2 fleet fields"
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
checks = {
    "git_commit": "abc123def456",
    "config_version": "cfg-1.2.3",
    "health_status": "healthy",
}
for key, expected in checks.items():
    got = match.get(key)
    if got != expected:
        raise SystemExit(f"{key}: expected {expected!r}, got {got!r}")
for key, expected in [("cpu_percent", 12.5), ("memory_percent", 48.0), ("disk_percent", 71.0)]:
    got = float(match.get(key) or -1)
    if abs(got - expected) > 0.01:
        raise SystemExit(f"{key}: expected {expected}, got {got}")
services = match.get("enabled_services") or []
if sorted(services) != ["svc-01", "svc-06"]:
    raise SystemExit(f"enabled_services expected svc-01/svc-06, got {services!r}")
if not match.get("last_seen_at"):
    raise SystemExit("last_seen_at missing")
print("OK phase-2 fleet fields present on list row")
PY

section "Live Beta appliance spot-check (optional)"
export PLATFORM_ADMIN_TOKEN
python3 - <<'PY'
import json, os, subprocess
token = os.environ.get("PLATFORM_ADMIN_TOKEN", "")
if not token:
    raise SystemExit(0)
raw = subprocess.check_output([
    "curl", "-fsS",
    "-H", f"Authorization: Bearer {token}",
    "http://localhost:8000/admin/appliances?q=niktiar-appliance&page_size=10",
], text=True)
for row in json.loads(raw).get("appliances") or []:
    if "junexis" in (row.get("appliance_name") or "").lower():
        svcs = row.get("enabled_services") or []
        cpu = row.get("cpu_percent")
        mem = row.get("memory_percent")
        disk = row.get("disk_percent")
        print(
            "Beta fleet row:",
            f"services={svcs}",
            f"cpu={cpu}",
            f"mem={mem}",
            f"disk={disk}",
            f"version={row.get('config_version') or row.get('git_commit')}",
        )
        if not svcs:
            raise SystemExit("Beta appliance enabled_services still empty")
        if cpu is None or mem is None or disk is None:
            raise SystemExit("Beta appliance resource metrics still missing")
        break
else:
    print("No niktiar-appliance row (skipped live spot-check).")
PY

echo
echo "======================================================================"
echo "KB-099 VALIDATION PASSED"
echo "======================================================================"
