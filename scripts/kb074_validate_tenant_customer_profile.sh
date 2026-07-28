#!/usr/bin/env bash
# KB-074: Validate tenant customer profile fields (schema + API models + Admin UI).
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

check "migration file exists" test -f postgres/init/010_kb074_tenant_customer_profile.sql
check "migration adds primary_contact_email" file_has postgres/init/010_kb074_tenant_customer_profile.sql "primary_contact_email"
check "migration adds country" file_has postgres/init/010_kb074_tenant_customer_profile.sql "country"
check "migration adds address_line1" file_has postgres/init/010_kb074_tenant_customer_profile.sql "address_line1"
check "schema TenantCreateRequest requires primary contact" \
  file_has backend-api/app/schemas/tenants.py "primary_contact_name: str"
check "schema TenantCreateRequest requires country" \
  file_has backend-api/app/schemas/tenants.py "country: str = Field"
check "tenant create INSERT includes profile columns" \
  file_has backend-api/app/api/routes/tenant_management.py "primary_contact_name, primary_contact_email"
check "admin list returns country" \
  file_has backend-api/app/api/routes/admin.py "t.country,"
check "Admin UI create form has primary contact" \
  file_has frontend-admin/src/pages/TenantsPage.tsx "primary_contact_name"
check "Admin UI create form has country" \
  file_has frontend-admin/src/pages/TenantsPage.tsx 'Country'
check "Admin API types include profile" \
  file_has frontend-admin/src/api/admin.ts "primary_contact_email: string"

# Live DB columns (if compose up)
if docker compose exec -T postgres pg_isready -U mssp_admin -d mssp_control >/dev/null 2>&1; then
  COLS=$(docker compose exec -T postgres psql -U mssp_admin -d mssp_control -Atc \
    "SELECT count(*) FROM information_schema.columns WHERE table_name='tenants' AND column_name IN (
      'primary_contact_name','primary_contact_email','primary_contact_phone',
      'secondary_contact_name','secondary_contact_email','secondary_contact_phone',
      'billing_email','address_line1','address_line2','city','state_region',
      'postal_code','country','website','industry'
    );")
  check "live DB has 15 profile columns" test "$COLS" = "15"
else
  echo "SKIP: live DB not ready"
fi

echo "KB-074 checks: pass=$pass fail=$fail"
test "$fail" -eq 0
