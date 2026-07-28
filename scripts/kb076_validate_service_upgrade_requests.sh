#!/usr/bin/env bash
# KB-076: Validate service upgrade request flow (vuln subscription interest).
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"
pass=0
fail=0
check() {
  local name="$1"
  shift
  if "$@"; then
    echo "PASS: $name"
    pass=$((pass + 1))
  else
    echo "FAIL: $name"
    fail=$((fail + 1))
  fi
}
file_has() { grep -qE "$2" "$1"; }

check "migration exists" test -f postgres/init/012_kb076_service_upgrade_requests.sql
check "migration has requirements_summary" \
  file_has postgres/init/012_kb076_service_upgrade_requests.sql "requirements_summary"
check "API create endpoint" \
  file_has backend-api/app/api/routes/entitlements.py "service-upgrade-requests"
check "API admin list endpoint" \
  file_has backend-api/app/api/routes/entitlements.py "/admin/service-upgrade-requests"
check "customer page has upgrade form" \
  file_has frontend-customer/src/pages/VulnerabilitiesPage.tsx "Tell us what you need"
check "customer page has scan scope" \
  file_has frontend-customer/src/pages/VulnerabilitiesPage.tsx "scan_scope"
check "customer API helper" \
  file_has frontend-customer/src/api/customer.ts "createServiceUpgradeRequest"
check "admin API helper" \
  file_has frontend-admin/src/api/admin.ts "getServiceUpgradeRequests"
check "admin approve-enable endpoint" \
  file_has backend-api/app/api/routes/entitlements.py "approve-enable"
check "admin UI approve action" \
  file_has frontend-admin/src/pages/VulnerabilitiesPage.tsx "Approve &amp; enable"

if docker compose exec -T postgres pg_isready -U mssp_admin -d mssp_control >/dev/null 2>&1; then
  EXISTS=$(docker compose exec -T postgres psql -U mssp_admin -d mssp_control -Atc \
    "SELECT to_regclass('public.service_upgrade_requests') IS NOT NULL;")
  check "live table service_upgrade_requests exists" test "$EXISTS" = "t"
else
  echo "SKIP: live DB not ready"
fi

echo "KB-076 checks: pass=$pass fail=$fail"
test "$fail" -eq 0
