#!/usr/bin/env bash
# KB-069: Validate Greenbone → control-plane vulnerability adapter + Admin UI wiring.
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-069: Validate Vulnerability Control-Plane Adapter"
echo "======================================================================"

fail() { echo; echo "VALIDATION FAILED: $1" >&2; exit 1; }
section() { echo; echo "----------------------------------------------------------------------"; echo "$1"; echo "----------------------------------------------------------------------"; }

section "1. Required files"
for f in \
  postgres/init/004_kb069_vulnerabilities.sql \
  backend-api/app/schemas/vulnerabilities.py \
  backend-api/app/services/vuln_sync_service.py \
  backend-api/app/api/routes/vuln_sync.py \
  backend-api/app/api/routes/vulnerability_management.py \
  frontend-admin/src/pages/VulnerabilitiesPage.tsx \
  docs/KB069_GREENBONE_CONTROL_PLANE_ADAPTER.md \
  scripts/kb069_create_vulnerabilities.sh \
  scripts/kb069_validate_greenbone_control_plane_adapter.sh \
  scripts/kb069_ingest_sample_finding.sh
do
  [ -f "$f" ] || fail "$f missing"
  echo "found: $f"
done

section "2. Safety checks"
grep -q "X-Vuln-Sync-Key" backend-api/app/api/routes/vuln_sync.py || fail "missing sync key header"
grep -q "raw_finding" postgres/init/004_kb069_vulnerabilities.sql || fail "raw_finding column missing"
grep -q "related_vulnerability_id" postgres/init/004_kb069_vulnerabilities.sql || fail "rec link missing"
grep -q "vulnerabilities" frontend-admin/src/components/Layout.tsx || fail "nav missing"
grep -q "VulnerabilitiesPage" frontend-admin/src/App.tsx || fail "route missing"
grep -q "vuln_sync_router" backend-api/app/main.py || fail "main.py not wired"
grep -q "VULN_SYNC_API_KEY_FILE" docker-compose.yml || fail "compose secret mount missing"
# Customer frontend must not gain raw vuln APIs in this KB
git grep -n "vulnerabilities" -- frontend-customer/ >/dev/null 2>&1 && fail "customer frontend references vulnerabilities" || echo "OK: customer frontend untouched for vulns"
echo "OK: safety"

section "3. Schema present in live DB (if postgres up)"
if docker compose ps postgres 2>/dev/null | grep -q Up; then
  TABLE_OK="$(docker compose exec -T postgres psql -X -q -t -A -U mssp_admin -d mssp_control -c "
SELECT count(*) FROM information_schema.tables
WHERE table_schema='public' AND table_name='vulnerabilities';
" 2>/dev/null || echo 0)"
  [ "$TABLE_OK" = "1" ] || fail "vulnerabilities table not applied — run scripts/kb069_create_vulnerabilities.sh"
  echo "OK: live table present"
else
  echo "SKIP: postgres not running"
fi

section "4. OpenAPI paths (if API up)"
if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
  curl -fsS http://localhost:8000/openapi.json | python3 -c '
import json,sys
doc=json.load(sys.stdin)
paths=doc.get("paths",{})
needed=(
  "/integrations/vuln/sync",
  "/admin/vulnerabilities",
  "/admin/vulnerabilities/{vulnerability_id}",
  "/admin/vulnerabilities/{vulnerability_id}/promote-recommendation",
)
for p in needed:
    assert p in paths, p
print("OK: openapi paths")
'
else
  echo "SKIP: API not reachable"
fi

section "5. Final"
echo "======================================================================"
echo "KB-069 GREENBONE CONTROL PLANE ADAPTER VALIDATION PASSED"
echo "======================================================================"
