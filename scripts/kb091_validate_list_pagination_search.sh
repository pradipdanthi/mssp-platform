#!/usr/bin/env bash
# KB-091: Validate Alerts/Incidents list pagination + search filters.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; exit 1; }

# Source helpers
grep -q 'clamp_pagination' backend-api/app/services/list_pagination.py \
  || fail "list_pagination helper missing"
grep -q 'page_size' backend-api/app/api/routes/admin.py \
  || fail "admin alerts/incidents missing page_size"
grep -q 'page_size' backend-api/app/api/routes/customer.py \
  || fail "customer alerts/incidents missing page_size"
grep -q 'ListToolbar' frontend-admin/src/pages/AlertsPage.tsx \
  || fail "admin AlertsPage missing ListToolbar"
grep -q 'ListToolbar' frontend-admin/src/pages/IncidentsPage.tsx \
  || fail "admin IncidentsPage missing ListToolbar"
grep -q 'ListToolbar' frontend-customer/src/pages/AlertsPage.tsx \
  || fail "customer AlertsPage missing ListToolbar"
grep -q 'ListToolbar' frontend-customer/src/pages/IncidentsPage.tsx \
  || fail "customer IncidentsPage missing ListToolbar"
grep -q 'CustomerListFilters' frontend-customer/src/api/customer.ts \
  || fail "customer API missing list filters"
grep -q 'page_size' frontend-admin/src/api/admin.ts \
  || fail "admin TriageListFilters missing page_size"

# Live API smoke (requires running stack + platform admin JWT via env or skip)
if [[ -n "${MSSP_ADMIN_TOKEN:-}" ]]; then
  AUTH="Authorization: Bearer ${MSSP_ADMIN_TOKEN}"
  body="$(curl -fsS -H "$AUTH" "http://127.0.0.1:8000/admin/incidents?page=1&page_size=5")"
  echo "$body" | grep -q '"total"' || fail "admin incidents missing total"
  echo "$body" | grep -q '"page"' || fail "admin incidents missing page"
  echo "$body" | grep -q '"has_next"' || fail "admin incidents missing has_next"
  body="$(curl -fsS -H "$AUTH" "http://127.0.0.1:8000/admin/alerts?page=1&page_size=5")"
  echo "$body" | grep -q '"total"' || fail "admin alerts missing total"
  pass "live admin list pagination"
else
  pass "static checks only (set MSSP_ADMIN_TOKEN for live API)"
fi

pass "kb091 list pagination + search filters"
