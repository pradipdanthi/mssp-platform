#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail() { echo "FAIL: $*"; exit 1; }
pass() { echo "PASS: $*"; }

for f in \
  backend-api/app/api/routes/edr.py \
  backend-api/app/services/edr_actions.py \
  backend-api/app/services/edr_process_tree.py \
  backend-api/app/services/shuffle_edr_client.py \
  postgres/init/014_kb083_edr_actions.sql; do
  [[ -f "$f" ]] || fail "missing $f"
done

grep -q 'edr_router' backend-api/app/main.py || fail "main.py missing edr router"
grep -q 'persist_wazuh_alert_enrichment' backend-api/app/api/routes/soc_sync.py || fail "wazuh ingress enrichment"
grep -q 'customer_admin' backend-api/app/services/edr_actions.py || fail "customer_admin RBAC"
grep -q 'EDR_SHUFFLE_FORENSICS_WORKFLOW' backend-api/app/services/shuffle_edr_client.py || fail "forensics workflow env"

python3 -m py_compile \
  backend-api/app/api/routes/edr.py \
  backend-api/app/services/edr_actions.py \
  backend-api/app/services/edr_process_tree.py \
  backend-api/app/services/edr_mitre.py \
  backend-api/app/services/edr_metrics.py || fail "py_compile"

pass "KB-083 EDR/MXDR validation complete"
