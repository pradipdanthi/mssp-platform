#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-067: Validate Enterprise Monthly Report Export"
echo "======================================================================"

fail() {
  echo; echo "VALIDATION FAILED: $1"
  docker compose logs --tail=50 backend-api 2>/dev/null || true
  exit 1
}

section() {
  echo; echo "----------------------------------------------------------------------"; echo "$1"; echo "----------------------------------------------------------------------"
}

section "1. Files"
for f in \
  backend-api/app/services/report_snapshot_service.py \
  backend-api/app/services/report_export_service.py \
  backend-api/app/schemas/report_snapshot.py \
  frontend-admin/src/pages/ReportsPage.tsx \
  frontend-customer/src/pages/ReportDetailPage.tsx \
  docs/KB067_ENTERPRISE_MONTHLY_REPORT_EXPORT.md \
  scripts/kb067_validate_enterprise_monthly_report_export.sh
do
  [ -f "$f" ] || fail "missing $f"
  echo "found: $f"
done

section "2. Dependencies pinned"
grep -q 'reportlab==' backend-api/requirements.txt || fail "reportlab missing"
grep -q 'openpyxl==' backend-api/requirements.txt || fail "openpyxl missing"
docker compose exec -T backend-api python -c 'import reportlab, openpyxl; print("ok", reportlab.Version)' \
  || fail "reportlab/openpyxl not importable in backend container"

section "3. OpenAPI paths"
OPENAPI=$(curl -fsS "$API_BASE/openapi.json")
echo "$OPENAPI" | grep -q 'refresh-metrics' || fail "missing refresh-metrics"
echo "$OPENAPI" | grep -q 'download.pdf' || fail "missing download.pdf"
echo "$OPENAPI" | grep -q 'download.xlsx' || fail "missing download.xlsx"
echo "OK"

section "4. Health + unauthenticated denied"
curl -fsS "$API_BASE/health" | grep -q '"api":"ok"' || fail "health"
CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$API_BASE/admin/reports")
[[ "$CODE" == "401" ]] || fail "admin reports expected 401 got $CODE"
CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$API_BASE/customer/reports/DEMO/00000000-0000-0000-0000-000000000001/download.pdf")
[[ "$CODE" == "401" ]] || fail "customer pdf expected 401 got $CODE"
echo "OK"

section "5. Source markers"
grep -q 'Download PDF' frontend-admin/src/pages/ReportsPage.tsx || fail "admin PDF button"
grep -q 'Download Excel' frontend-customer/src/pages/ReportDetailPage.tsx || fail "customer Excel button"
grep -q 'build_snapshot' backend-api/app/services/report_snapshot_service.py || fail "snapshot builder"
echo "OK"

echo
echo "======================================================================"
echo "KB-067 ENTERPRISE MONTHLY REPORT EXPORT VALIDATION PASSED"
echo "======================================================================"
