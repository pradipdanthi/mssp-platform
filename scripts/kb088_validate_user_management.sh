#!/usr/bin/env bash
# KB-088: Tenant + customer user management APIs and UI wiring checks.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PASS=0
FAIL=0
ok() { echo "PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

grep -q 'create_tenant_customer_user' backend-api/app/api/routes/tenant_management.py && \
  ok 'admin POST /admin/tenants/{id}/users' || bad 'admin tenant user create route'
grep -q 'reset_tenant_customer_user_password' backend-api/app/api/routes/tenant_management.py && \
  ok 'admin PATCH tenant user password' || bad 'admin tenant user password route'
grep -q 'createTenantCustomerUser' frontend-admin/src/api/admin.ts && \
  ok 'admin API client tenant user helpers' || bad 'admin API client'
grep -q 'TenantCustomerUsersPanel' frontend-admin/src/pages/TenantsPage.tsx && \
  ok 'TenantsPage uses TenantCustomerUsersPanel' || bad 'TenantsPage panel'
grep -q 'RowActionsMenu' frontend-customer/src/pages/UsersPage.tsx && \
  ok 'customer UsersPage row actions' || bad 'customer UsersPage'
grep -q 'ConfirmDangerModal' frontend-customer/src/pages/UsersPage.tsx && \
  ok 'customer UsersPage danger confirm' || bad 'customer danger modal'
grep -q '/password' frontend-customer/src/pages/UsersPage.tsx && \
  ok 'customer password reset UI' || bad 'customer password reset'

if [[ "$FAIL" -eq 0 ]]; then
  echo "KB-088 user management validation: $PASS checks PASS"
  exit 0
fi
echo "KB-088 user management validation: $FAIL failed, $PASS passed"
exit 1
