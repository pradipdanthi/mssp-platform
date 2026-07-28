#!/usr/bin/env bash
# KB-075: Validate contract-ready customer onboarding (fields + create flow wiring).
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

check "migration exists" test -f postgres/init/011_kb075_contract_ready_onboarding.sql
check "migration has legal_name" file_has postgres/init/011_kb075_contract_ready_onboarding.sql "legal_name"
check "migration has contract_reference" file_has postgres/init/011_kb075_contract_ready_onboarding.sql "contract_reference"
check "migration has licensed_endpoints" file_has postgres/init/011_kb075_contract_ready_onboarding.sql "licensed_endpoints"
check "schema has EntitlementsOnCreate" file_has backend-api/app/schemas/tenants.py "class EntitlementsOnCreate"
check "schema has PortalAdminOnCreate" file_has backend-api/app/schemas/tenants.py "class PortalAdminOnCreate"
check "schema has OnboardResult" file_has backend-api/app/schemas/tenants.py "class OnboardResult"
check "create inserts commercial columns" file_has backend-api/app/api/routes/tenant_management.py "legal_name, tax_id, contract_reference"
check "create upserts entitlements" file_has backend-api/app/api/routes/tenant_management.py "upsert_tenant_entitlements"
check "create can make portal admin" file_has backend-api/app/api/routes/tenant_management.py "_create_portal_admin"
check "entitlements helper exported" file_has backend-api/app/api/routes/entitlements.py "def upsert_tenant_entitlements"
check "Admin UI has CreateEntitlementsFields" file_has frontend-admin/src/pages/TenantsPage.tsx "CreateEntitlementsFields"
check "Admin UI requires portal admin section" \
  file_has frontend-admin/src/pages/TenantsPage.tsx "Customer portal admin \\(required\\)"
check "Admin UI has contract reference" file_has frontend-admin/src/pages/TenantsPage.tsx "contract_reference"
check "portal_admin required in schema" \
  file_has backend-api/app/schemas/tenants.py "portal_admin: PortalAdminOnCreate"
check "Admin API types require portal_admin" \
  file_has frontend-admin/src/api/admin.ts "portal_admin: PortalAdminOnCreate"
check "contract options picklists exist" test -f frontend-admin/src/data/contractOptions.ts
check "UI states every-customer path" \
  file_has frontend-admin/src/pages/TenantsPage.tsx "standard path for every customer"
if docker compose exec -T postgres pg_isready -U mssp_admin -d mssp_control >/dev/null 2>&1; then
  COLS=$(docker compose exec -T postgres psql -U mssp_admin -d mssp_control -Atc \
    "SELECT count(*) FROM information_schema.columns WHERE table_name='tenants' AND column_name IN (
      'legal_name','tax_id','contract_reference','contract_start_date','contract_end_date',
      'licensed_endpoints','data_residency','preferred_language','company_size'
    );")
  check "live DB has 9 commercial columns" test "$COLS" = "9"
else
  echo "SKIP: live DB not ready"
fi

echo "KB-075 checks: pass=$pass fail=$fail"
test "$fail" -eq 0
