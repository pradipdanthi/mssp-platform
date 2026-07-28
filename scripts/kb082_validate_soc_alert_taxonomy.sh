#!/usr/bin/env bash
# KB-082: SOC all-device alert taxonomy (admin API + UI wiring)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail() { echo "FAIL: $*"; exit 1; }
pass() { echo "PASS: $*"; }

[[ -f backend-api/app/services/soc_alert_taxonomy.py ]] || fail "missing soc_alert_taxonomy.py"
grep -q 'derive_asset_category' backend-api/app/services/soc_alert_taxonomy.py || fail "derive_asset_category missing"
grep -q 'asset_category' backend-api/app/api/routes/admin.py || fail "admin alerts asset_category filter missing"
grep -q 'taxonomy-summary' backend-api/app/api/routes/admin.py || fail "taxonomy-summary endpoint missing"
grep -q 'AlertTaxonomyNav' frontend-admin/src/components/AlertTaxonomyNav.tsx || fail "AlertTaxonomyNav missing"
grep -q 'asset_category' frontend-admin/src/pages/AlertsPage.tsx || fail "AlertsPage category wiring missing"
grep -q 'alerts-page-layout' frontend-admin/src/styles.css || fail "taxonomy CSS missing"
grep -q 'getAlertTaxonomySummary' frontend-admin/src/api/admin.ts || fail "admin API taxonomy client missing"

python3 -m py_compile backend-api/app/services/soc_alert_taxonomy.py || fail "py_compile taxonomy"

if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
  code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/admin/alerts/taxonomy-summary || true)
  if [[ "$code" == "401" || "$code" == "403" ]]; then
    pass "taxonomy-summary requires auth ($code)"
  elif [[ "$code" == "200" ]]; then
    pass "taxonomy-summary reachable (200)"
  else
    fail "taxonomy-summary unexpected HTTP $code"
  fi
else
  echo "SKIP: API not running — start stack to live-test taxonomy-summary"
fi

pass "KB-082 SOC alert taxonomy validation complete"
