#!/usr/bin/env bash
# KB-112: Validate NikTiar Sovereign Edge foundation (mode, helpers, admin UI).
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"

pass=0
fail=0
section() { echo; echo "=== $1 ==="; }
ok() { echo "PASS: $1"; pass=$((pass + 1)); }
bad() { echo "FAIL: $1"; fail=$((fail + 1)); }

section "1. Documentation"
test -f docs/KB112_SOVEREIGN_EDGE_TEST_PLAN.md && ok "KB112 test plan exists" || bad "KB112 test plan missing"
grep -q "sovereign_edge" docs/KB112_SOVEREIGN_EDGE_TEST_PLAN.md && ok "test plan mentions sovereign_edge" || bad "test plan mode"

section "2. Schema"
test -f postgres/init/049_sovereign_edge_deployment_mode.sql && ok "migration 049 exists" || bad "migration 049"
grep -q "sovereign_edge" postgres/init/049_sovereign_edge_deployment_mode.sql && ok "DB constraint includes sovereign_edge" || bad "DB constraint"

section "3. Backend service module"
test -f backend-api/app/services/sovereign_edge.py && ok "sovereign_edge.py exists" || bad "sovereign_edge.py"
grep -q "offline_license_delivery" backend-api/app/services/sovereign_edge.py && ok "offline license helper" || bad "offline license"
grep -q "default_cloud_egress_enabled" backend-api/app/services/sovereign_edge.py && ok "egress default helper" || bad "egress helper"
grep -q "sovereign_edge" backend-api/app/schemas/tenants.py && ok "schema literal" || bad "schema literal"
grep -q "offline_license_manual" backend-api/app/services/capability_fulfillment_service.py && ok "fulfillment skips channel push" || bad "fulfillment skip"
grep -q "sovereign_onboard_next_steps" backend-api/app/api/routes/tenant_management.py && ok "onboard next steps wired" || bad "onboard steps"

section "4. Admin UI"
grep -q "sovereign_edge" frontend-admin/src/api/admin.ts && ok "admin API type" || bad "admin API type"
grep -q "Sovereign Edge" frontend-admin/src/pages/TenantsPage.tsx && ok "TenantsPage option" || bad "TenantsPage option"

section "5. Unit tests"
if docker compose exec -T backend-api python -m unittest tests.test_sovereign_edge -q 2>/dev/null; then
  ok "test_sovereign_edge unittest (backend container)"
elif (cd backend-api && PYTHONPATH=. python3 -m unittest tests.test_sovereign_edge -q 2>/dev/null); then
  ok "test_sovereign_edge unittest (host)"
else
  bad "test_sovereign_edge unittest"
fi

section "6. Live DB (optional)"
if docker compose exec -T postgres psql -U mssp_admin -d mssp_control -Atc \
  "SELECT 1 FROM pg_constraint WHERE conname='tenants_deployment_mode_check' AND pg_get_constraintdef(oid) LIKE '%sovereign_edge%';" 2>/dev/null | grep -q 1; then
  ok "live DB constraint includes sovereign_edge"
else
  echo "SKIP: live DB not updated yet — apply postgres/init/049_sovereign_edge_deployment_mode.sql"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "KB-112 SOVEREIGN EDGE FOUNDATION VALIDATION PASSED ($pass checks)"
  exit 0
fi
echo "KB-112 SOVEREIGN EDGE FOUNDATION VALIDATION FAILED ($fail failed / $pass passed)"
exit 1
