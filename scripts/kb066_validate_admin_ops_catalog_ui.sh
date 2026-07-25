#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3000"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-066: Validate Admin Ops Catalog (recs/reports/assets/audit)"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1"
  docker compose logs --tail=40 backend-api 2>/dev/null || true
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

section "1. Files exist"
REQUIRED=(
  "backend-api/app/api/routes/recommendation_management.py"
  "backend-api/app/api/routes/admin_ops.py"
  "backend-api/app/schemas/recommendations_admin.py"
  "backend-api/app/schemas/admin_ops.py"
  "frontend-admin/src/pages/RecommendationsPage.tsx"
  "frontend-admin/src/pages/ReportsPage.tsx"
  "frontend-admin/src/pages/AssetsPage.tsx"
  "frontend-admin/src/pages/AuditLogsPage.tsx"
  "scripts/kb066_validate_admin_ops_catalog_ui.sh"
)
for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f missing"
  echo "found: $f"
done

section "2. Source markers"
grep -q "Add Recommendation" frontend-admin/src/pages/RecommendationsPage.tsx || fail "recs UI"
grep -q "Add Report" frontend-admin/src/pages/ReportsPage.tsx || fail "reports UI"
grep -q "Add Asset" frontend-admin/src/pages/AssetsPage.tsx || fail "assets UI"
grep -q "Audit Log" frontend-admin/src/pages/AuditLogsPage.tsx || fail "audit UI"
grep -q 'to: "/reports"' frontend-admin/src/components/Layout.tsx || fail "nav reports"
grep -q 'to: "/assets"' frontend-admin/src/components/Layout.tsx || fail "nav assets"
grep -q 'to: "/audit"' frontend-admin/src/components/Layout.tsx || fail "nav audit"
grep -q "recommendation_management_router" backend-api/app/main.py || fail "main recs router"
grep -q "admin_ops_router" backend-api/app/main.py || fail "main ops router"
echo "OK"

section "3. OpenAPI paths present"
OPENAPI=$(curl -fsS "$API_BASE/openapi.json")
echo "$OPENAPI" | grep -q '"/admin/recommendations/{recommendation_id}"' || fail "missing rec detail path"
echo "$OPENAPI" | grep -q '"/admin/reports"' || fail "missing reports path"
echo "$OPENAPI" | grep -q '"/admin/assets"' || fail "missing assets path"
echo "$OPENAPI" | grep -q '"/admin/audit-logs"' || fail "missing audit path"
echo "OK: OpenAPI includes new admin ops paths"

section "4. Frontend + health"
curl -fsS "$API_BASE/health" | grep -q '"api":"ok"' || fail "health"
curl -fsS -o /dev/null -w "%{http_code}" "$FRONTEND_BASE/" | grep -Eq '200|304' || fail "frontend"
docker compose exec -T frontend-admin sh -c 'grep -q "Add Recommendation" /app/src/pages/RecommendationsPage.tsx' \
  || fail "container missing recs UI"
docker compose exec -T frontend-admin sh -c 'grep -q "Add Report" /app/src/pages/ReportsPage.tsx' \
  || fail "container missing reports UI"
echo "OK"

section "5. Unauthenticated write denied"
CODE=$(curl -sS -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" \
  -d '{"tenant_id":"00000000-0000-0000-0000-000000000001","title":"x","description":"y"}' \
  "$API_BASE/admin/recommendations")
[[ "$CODE" == "401" ]] || fail "POST recommendations expected 401 got $CODE"
CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$API_BASE/admin/reports")
[[ "$CODE" == "401" ]] || fail "GET reports expected 401 got $CODE"
CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$API_BASE/admin/assets")
[[ "$CODE" == "401" ]] || fail "GET assets expected 401 got $CODE"
CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$API_BASE/admin/audit-logs")
[[ "$CODE" == "401" ]] || fail "GET audit expected 401 got $CODE"
echo "OK: unauthenticated access denied"

echo
echo "======================================================================"
echo "KB-066 ADMIN OPS CATALOG UI VALIDATION PASSED"
echo "======================================================================"
