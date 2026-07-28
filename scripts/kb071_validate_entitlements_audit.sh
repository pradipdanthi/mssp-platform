#!/usr/bin/env bash
# KB-071: Validate entitlements + audit wiring (docs/API/UI surface).
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-071: Tenant entitlements + connected audit (validation)"
echo "======================================================================"

fail() { echo; echo "FAILED: $1"; exit 1; }
section() { echo; echo "----------------------------------------------------------------------"; echo "$1"; echo "----------------------------------------------------------------------"; }
pass() { echo "PASS: $1"; }

section "1. Schema + apply script"
[ -f postgres/init/005_kb071_tenant_entitlements.sql ] || fail "missing entitlements SQL"
[ -x scripts/kb071_create_entitlements.sh ] || fail "missing apply script"
TABLE_OK="$(docker compose exec -T postgres psql -X -q -t -A -U mssp_admin -d mssp_control -c "
SELECT count(*) FROM information_schema.tables
WHERE table_schema='public' AND table_name='tenant_entitlements';
")"
[ "$TABLE_OK" = "1" ] || fail "tenant_entitlements table missing"
pass "tenant_entitlements present"

section "2. Backend routes live"
curl -fsS http://127.0.0.1:8000/health >/dev/null || fail "API health"
OPENAPI="$(curl -fsS http://127.0.0.1:8000/openapi.json)"
echo "$OPENAPI" | grep -q '/admin/tenants/{tenant_id}/entitlements' || fail "admin entitlements route missing"
echo "$OPENAPI" | grep -q '/customer/entitlements/{short_code}' || fail "customer entitlements route missing"
echo "$OPENAPI" | grep -q '/admin/audit-events' || fail "audit-events route missing"
pass "OpenAPI exposes entitlements + audit-events"

section "3. Admin UI surfaces"
[ -f frontend-admin/src/components/RowActionsMenu.tsx ] || fail "RowActionsMenu missing"
[ -f frontend-admin/src/components/ConfirmDangerModal.tsx ] || fail "ConfirmDangerModal missing"
[ -f frontend-admin/src/components/SubscriptionEntitlementsPanel.tsx ] || fail "Subscription panel missing"
grep -q 'RowActionsMenu' frontend-admin/src/pages/TenantsPage.tsx || fail "TenantsPage kebab missing"
grep -q 'RowActionsMenu' frontend-admin/src/pages/UsersPage.tsx || fail "UsersPage kebab missing"
grep -q 'RowActionsMenu' frontend-admin/src/pages/AppliancesPage.tsx || fail "AppliancesPage kebab missing"
grep -q 'Export CSV' frontend-admin/src/pages/AuditLogsPage.tsx || fail "Audit export missing"
grep -q 'putTenantEntitlements' frontend-admin/src/api/admin.ts || fail "admin entitlements API helper missing"
pass "Admin kebab + subscription + audit UI present"

section "4. Customer adaptive vulnerabilities"
[ -f frontend-customer/src/pages/VulnerabilitiesPage.tsx ] || fail "VulnerabilitiesPage missing"
grep -q 'getCustomerEntitlements' frontend-customer/src/api/customer.ts || fail "customer entitlements helper missing"
grep -q '/vulnerabilities' frontend-customer/src/App.tsx || fail "customer route missing"
grep -q 'Vulnerabilities' frontend-customer/src/components/Layout.tsx || fail "customer nav missing"
! grep -R --include='*.ts' --include='*.tsx' -n '"/admin' frontend-customer/src/pages/VulnerabilitiesPage.tsx \
  frontend-customer/src/api/customer.ts >/dev/null 2>&1 || fail "customer files must not call /admin"
if grep -R --include='*.ts' --include='*.tsx' -iE \
  'nuclei|vuls|greenbone|wazuh|suricata|zeek|thehive|shuffle|misp|velociraptor|openvas' \
  frontend-customer/src/pages frontend-customer/src/components >/dev/null 2>&1; then
  fail "customer UI must not expose backend engine names"
fi
pass "Customer UI has no engine brand strings (pages/components)"

echo
echo "KB-071 VALIDATE ENTITLEMENTS + AUDIT PASSED"
