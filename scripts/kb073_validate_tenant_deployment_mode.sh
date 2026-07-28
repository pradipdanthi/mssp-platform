#!/usr/bin/env bash
# KB-073: Validate tenant deployment mode (schema + API + admin UI source).
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"

pass=0
fail=0
section() { echo; echo "=== $1 ==="; }
ok() { echo "PASS: $1"; pass=$((pass + 1)); }
bad() { echo "FAIL: $1"; fail=$((fail + 1)); }

section "1. Schema files"
test -f postgres/init/008_kb073_tenant_deployment_mode.sql && ok "migration file exists" || bad "migration missing"
grep -q "deployment_mode" postgres/init/008_kb073_tenant_deployment_mode.sql && ok "deployment_mode in migration" || bad "deployment_mode missing"
grep -q "cloud_provider" postgres/init/008_kb073_tenant_deployment_mode.sql && ok "cloud_provider in migration" || bad "cloud_provider missing"
grep -q "on_prem_appliance" postgres/init/008_kb073_tenant_deployment_mode.sql && ok "on_prem_appliance mode" || bad "on_prem_appliance missing"
grep -q "cloud_appliance" postgres/init/009_kb073b_cloud_appliance_mode.sql && ok "cloud_appliance migration" || bad "cloud_appliance migration"

section "2. Live DB columns"
COLS="$(docker compose exec -T postgres psql -U mssp_admin -d mssp_control -Atc \
  "SELECT column_name FROM information_schema.columns WHERE table_name='tenants' AND column_name IN ('deployment_mode','cloud_provider') ORDER BY 1;")"
echo "$COLS" | grep -qx "cloud_provider" && ok "DB cloud_provider" || bad "DB cloud_provider"
echo "$COLS" | grep -qx "deployment_mode" && ok "DB deployment_mode" || bad "DB deployment_mode"

section "3. Backend schemas / routes"
grep -q "DeploymentModeLiteral" backend-api/app/schemas/tenants.py && ok "schema literals" || bad "schema literals"
grep -q "deployment_mode" backend-api/app/api/routes/tenant_management.py && ok "tenant_management uses deployment_mode" || bad "tenant_management"
grep -q "deployment_mode" backend-api/app/api/routes/admin.py && ok "admin list includes deployment_mode" || bad "admin list"

section "4. Admin UI"
grep -q "deployment_mode" frontend-admin/src/api/admin.ts && ok "admin API types" || bad "admin API types"
grep -q "deployment_mode" frontend-admin/src/pages/TenantsPage.tsx && ok "TenantsPage form" || bad "TenantsPage"
grep -q "on_prem_appliance" frontend-admin/src/pages/TenantsPage.tsx && ok "UI has on_prem_appliance" || bad "UI mode option"
grep -q "cloud_appliance" frontend-admin/src/pages/TenantsPage.tsx && ok "UI has cloud_appliance" || bad "UI cloud_appliance"
grep -q "Cloud with appliance" frontend-admin/src/pages/TenantsPage.tsx && ok "UI label Cloud with appliance" || bad "UI label"
grep -q "modeFilter" frontend-admin/src/pages/TenantsPage.tsx && ok "list filter chips" || bad "list filter"

section "5. OpenAPI paths still present"
curl -fsS http://localhost:8000/openapi.json | jq -e '.paths["/admin/tenants"]' >/dev/null \
  && ok "POST/GET /admin/tenants in OpenAPI" || bad "OpenAPI tenants"

echo
if [ "$fail" -eq 0 ]; then
  echo "KB-073 TENANT DEPLOYMENT MODE VALIDATION PASSED ($pass checks)"
  exit 0
fi
echo "KB-073 TENANT DEPLOYMENT MODE VALIDATION FAILED ($fail failed / $pass passed)"
exit 1
