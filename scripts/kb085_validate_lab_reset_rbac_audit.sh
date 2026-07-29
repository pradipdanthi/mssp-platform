#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
pass=0; fail=0
check(){ local n="$1"; shift; if "$@"; then echo "PASS: $n"; pass=$((pass+1)); else echo "FAIL: $n"; fail=$((fail+1)); fi; }

check "purge script" test -f scripts/purge_test_data.py
check "provision script" test -f scripts/kb085_purge_and_provision_lab.sh
check "audit migration" test -f postgres/init/016_kb085_audit_enrichment.sql
check "customer users route" grep -q 'customer_users_router' backend-api/app/main.py
check "audit routers" grep -q 'audit_admin_router' backend-api/app/main.py
check "v1 customers alias" grep -q 'admin_customers_v1_router' backend-api/app/main.py
check "staff-scoped users list" grep -q 'scope=staff' backend-api/app/api/routes/user_management.py
check "tenant users endpoint" grep -q 'tenant_id}/users' backend-api/app/api/routes/tenant_management.py
check "customer Users page" test -f frontend-customer/src/pages/UsersPage.tsx
check "customer Audit page" test -f frontend-customer/src/pages/AuditLogsPage.tsx
check "network_appliance taxonomy" grep -q 'network_appliance' backend-api/app/services/soc_alert_taxonomy.py

if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
  check "openapi customer users" bash -c 'curl -fsS http://localhost:8000/openapi.json | grep -q "/customer/users/"'
  check "openapi v1 audit admin" bash -c 'curl -fsS http://localhost:8000/openapi.json | grep -q "/v1/admin/audit-logs"'
  check "openapi v1 customers" bash -c 'curl -fsS http://localhost:8000/openapi.json | grep -q "/v1/admin/customers"'
  if docker ps --format '{{.Names}}' | grep -qx mssp-postgres; then
    check "audit actor_email column" bash -c "docker exec mssp-postgres psql -U mssp_admin -d mssp_control -tAc \"SELECT 1 FROM information_schema.columns WHERE table_name='audit_logs' AND column_name='actor_email'\" | grep -q 1"
    check "lab tenants present" bash -c "docker exec mssp-postgres psql -U mssp_admin -d mssp_control -tAc \"SELECT count(*) FROM tenants WHERE short_code IN ('ALPHAWIN','BETALINUX')\" | grep -E '^[2]$'"
    check "lab customer admins" bash -c "docker exec mssp-postgres psql -U mssp_admin -d mssp_control -tAc \"SELECT count(*) FROM platform_users WHERE email IN ('admin@alphawin.com','admin@betalinux.com') AND role='customer_admin'\" | grep -E '^[2]$'"
  fi
fi

echo "----"
echo "KB-085 validation: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]] && echo "KB-085 PASS" || exit 1
