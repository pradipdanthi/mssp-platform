#!/usr/bin/env bash
set -euo pipefail

cd /opt/mssp-control

fail() {
  echo "VALIDATION FAILED: $1" >&2
  exit 1
}

required=(
  backend-api/app/schemas/alert_ingest.py
  backend-api/app/api/routes/appliance_alert_ingest.py
  backend-api/app/main.py
  docs/KB057_CUSTOMER_SAFE_LIVE_SOC_DATA_INTEGRATION.md
)

for file in "${required[@]}"; do
  [[ -f "$file" ]] || fail "$file is missing"
done

python3 - <<'PY'
import ast
from pathlib import Path

schema_path = Path("backend-api/app/schemas/alert_ingest.py")
tree = ast.parse(schema_path.read_text())
request = next(
    node for node in tree.body
    if isinstance(node, ast.ClassDef) and node.name == "ApplianceAlertIngestRequest"
)
fields = {
    node.target.id
    for node in request.body
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
}
expected = {
    "source_tool",
    "external_alert_id",
    "severity",
    "alert_title",
    "alert_description",
    "event_time",
    "destination_host",
}
if fields != expected:
    raise SystemExit(f"unsafe or missing ingest fields: {sorted(fields)}")

source = schema_path.read_text()
if 'ConfigDict(extra="forbid")' not in source:
    raise SystemExit('request schema must use extra="forbid"')

for path in (
    schema_path,
    Path("backend-api/app/api/routes/appliance_alert_ingest.py"),
    Path("backend-api/app/main.py"),
):
    ast.parse(path.read_text())
PY

route="backend-api/app/api/routes/appliance_alert_ingest.py"
for needle in \
  '"/alerts"' \
  'X-Appliance-ID' \
  'X-Appliance-API-Key' \
  'verify_appliance_credentials' \
  'INSERT INTO security_alerts' \
  'customer_visible' \
  'false' \
  'external_alert_id' \
  'pg_advisory_xact_lock'; do
  rg -Fq "$needle" "$route" || fail "$route missing required behavior: $needle"
done

rg -Fq "appliance_alert_ingest_router" backend-api/app/main.py \
  || fail "KB-057 router is not registered in main.py"

if git status --porcelain -- .env postgres/init docker-compose.yml 2>/dev/null | rg -q .; then
  fail "KB-057 must not change .env, postgres/init, or docker-compose.yml"
fi

echo "KB-057 CUSTOMER-SAFE LIVE SOC DATA INTEGRATION VALIDATION PASSED"
