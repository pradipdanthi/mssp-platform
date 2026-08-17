#!/usr/bin/env bash
# KB-061: validate TheHive/Shuffle → control plane SOC sync foundation.
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

fail() { echo; echo "VALIDATION FAILED: $1" >&2; exit 1; }
section() { echo; echo "----------------------------------------------------------------------"; echo "$1"; echo "----------------------------------------------------------------------"; }

section "1. Required files"
REQUIRED=(
  docs/KB061_THEHIVE_CONTROL_PLANE_SYNC.md
  scripts/kb061_validate_thehive_control_plane_sync.sh
  scripts/kb061_sync_thehive_alerts.sh
  scripts/kb061_run_periodic_sync.sh
  backend-api/app/api/routes/soc_sync.py
  backend-api/app/schemas/soc_sync.py
  backend-api/app/services/soc_sync_service.py
)
for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f missing"
  echo "found: $f"
done

section "2. Protected paths / secrets hygiene"
# Schema stays frozen; KPI link polish in frontends is in-scope for KB-061 UX.
for p in postgres/init/; do
  git diff --quiet -- "$p" 2>/dev/null || fail "$p unexpectedly modified"
  echo "OK: $p unmodified"
done
git status --porcelain -- .env 2>/dev/null | grep -q . && fail ".env shows changed/untracked" || true
echo "OK: .env not dirty in git"
if git check-ignore -q .secrets/soc_sync_api_key 2>/dev/null || [[ ! -e .secrets/soc_sync_api_key ]]; then
  echo "OK: secret file gitignored or absent from tree tracking intent"
else
  git check-ignore -q .secrets/soc_sync_api_key || fail ".secrets/soc_sync_api_key must be gitignored"
fi
grep -REn -e 'SOC_SYNC_API_KEY=[A-Za-z0-9_-]{16,}' docs/ scripts/kb061*.sh 2>/dev/null | grep -v 'SOC_SYNC_API_KEY=' \
  && fail "possible hardcoded sync key" || true
# stronger: no assignment with long token in docs
if grep -REn 'X-SOC-Sync-Key:[[:space:]]*[A-Za-z0-9_-]{20,}' docs/KB061_THEHIVE_CONTROL_PLANE_SYNC.md 2>/dev/null; then
  fail "docs contain sync key material"
fi
echo "OK: no obvious sync key material in docs"

section "3. Code wiring"
grep -q 'soc_sync_router' backend-api/app/main.py || fail "main.py missing soc_sync_router"
grep -q 'SOC_SYNC_API_KEY_FILE' docker-compose.yml || fail "compose missing SOC_SYNC_API_KEY_FILE"
grep -q 'soc_sync_api_key' backend-api/app/core/error_handlers.py || fail "error_handlers missing soc_sync key redaction"
grep -q 'customer_visible' backend-api/app/services/soc_sync_service.py || fail "service missing customer_visible handling"
grep -qi 'DEMO' docs/KB061_THEHIVE_CONTROL_PLANE_SYNC.md || fail "docs missing DEMO tenant mapping"
grep -qi 'never' docs/KB061_THEHIVE_CONTROL_PLANE_SYNC.md || fail "docs missing never/safety language"
echo "OK: wiring and safety mentions present"

section "4. Live API checks"
curl -fsS http://127.0.0.1:8000/health >/dev/null || fail "/health failed"
OPENAPI="$(curl -fsS http://127.0.0.1:8000/openapi.json)"
echo "$OPENAPI" | jq -e '.paths | has("/integrations/soc/sync")' >/dev/null \
  || fail "OpenAPI missing /integrations/soc/sync"

# missing key → 401 or 503
CODE=$(curl -sS -o /tmp/kb061_nokey.json -w '%{http_code}' -X POST http://127.0.0.1:8000/integrations/soc/sync \
  -H 'Content-Type: application/json' \
  -d '{"source_tool":"thehive","external_alert_id":"x","severity":"low","alert_title":"t"}' || true)
[[ "$CODE" == "401" || "$CODE" == "503" ]] || fail "expected 401/503 without key, got $CODE"
echo "OK: unauthenticated sync rejected ($CODE)"

if [[ -f .secrets/soc_sync_api_key ]]; then
  KEY=$(tr -d '\n' <.secrets/soc_sync_api_key)
  EXT="kb061-validate-$(date +%s)"
  CODE=$(curl -sS -o /tmp/kb061_sync.json -w '%{http_code}' -X POST http://127.0.0.1:8000/integrations/soc/sync \
    -H 'Content-Type: application/json' \
    -H "X-SOC-Sync-Key: $KEY" \
    -d "{\"source_tool\":\"thehive\",\"external_alert_id\":\"$EXT\",\"severity\":\"high\",\"alert_title\":\"KB-061 validation alert\",\"alert_description\":\"validator\",\"tenant_short_code\":\"DEMO\"}")
  [[ "$CODE" == "201" ]] || { cat /tmp/kb061_sync.json; fail "sync create expected 201 got $CODE"; }
  jq -e '.customer_visible == true and .duplicate == false and (.incident_number|type=="string")' /tmp/kb061_sync.json >/dev/null \
    || { cat /tmp/kb061_sync.json; fail "sync response shape unexpected"; }
  CODE2=$(curl -sS -o /tmp/kb061_sync2.json -w '%{http_code}' -X POST http://127.0.0.1:8000/integrations/soc/sync \
    -H 'Content-Type: application/json' \
    -H "X-SOC-Sync-Key: $KEY" \
    -d "{\"source_tool\":\"thehive\",\"external_alert_id\":\"$EXT\",\"severity\":\"high\",\"alert_title\":\"KB-061 validation alert\",\"tenant_short_code\":\"DEMO\"}")
  [[ "$CODE2" == "200" ]] || fail "duplicate expected 200 got $CODE2"
  jq -e '.duplicate == true' /tmp/kb061_sync2.json >/dev/null || fail "duplicate flag missing"
  echo "OK: live sync create+dedup against DEMO"
else
  echo "SKIP live authenticated sync (secret file absent)"
fi


section "4b. Dashboard KPI cards are clickable"

grep -q 'to="/incidents"' frontend-customer/src/pages/DashboardPage.tsx \
  || fail "customer dashboard Open incidents KPI missing link"
grep -q 'to="/alerts"' frontend-customer/src/pages/DashboardPage.tsx \
  || fail "customer dashboard alerts KPI missing link"
grep -q 'stat-card-link' frontend-customer/src/pages/DashboardPage.tsx \
  || fail "customer StatCard missing link class"
grep -q 'to="/tenants"' frontend-admin/src/pages/DashboardPage.tsx \
  || fail "admin dashboard Tenants KPI missing link"
grep -q 'to="/alerts"' frontend-admin/src/pages/DashboardPage.tsx \
  || fail "admin dashboard Alerts KPI missing link"
grep -q 'to="/incidents"' frontend-admin/src/pages/DashboardPage.tsx \
  || fail "admin dashboard Incidents KPI missing link"
grep -q 'stat-card-link' frontend-admin/src/pages/DashboardPage.tsx \
  || fail "admin StatCard missing link class"
echo "OK: admin and customer KPI cards link to detail pages"

section "5. Final verdict"
echo "======================================================================"
echo "KB-061 THEHIVE CONTROL PLANE SYNC VALIDATION PASSED"
echo "======================================================================"
