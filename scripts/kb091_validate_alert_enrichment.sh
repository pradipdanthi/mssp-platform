#!/usr/bin/env bash
# KB-091: alert field enrichment contracts (asset/IP/user/taxonomy).
set -euo pipefail
cd /opt/mssp-control

fail() { echo "VALIDATION FAILED: $1" >&2; exit 1; }
section() { echo; echo "---- $1 ----"; }

section "1. Code contracts"
grep -q 'wazuh_agent_id' backend-api/app/schemas/soc_sync.py || fail "schema missing wazuh_agent_id"
grep -q 'technical_summary' backend-api/app/schemas/soc_sync.py || fail "schema missing technical_summary"
grep -q '_resolve_protected_asset_id' backend-api/app/services/soc_sync_service.py || fail "missing asset resolve"
grep -q 'ai_technical_summary' backend-api/app/services/soc_sync_service.py || fail "missing tech summary insert"
grep -q 'asset_os_name' backend-api/app/api/routes/alert_incident_triage.py || fail "detail missing asset_os_name"
grep -q 'host.startswith("win-")' backend-api/app/services/soc_alert_taxonomy.py || fail "taxonomy missing WIN- fallback"
grep -q '_resolve_asset_id' backend-api/app/services/edr_ingress.py || fail "enrichment missing asset resolve"
echo "OK: enrichment contracts present"

grep -q 'apply_soc_enrichment' backend-api/app/services/soc_alert_taxonomy.py \
  || fail "missing apply_soc_enrichment"
grep -q 'synthesize_soc_guidance' backend-api/app/services/soc_alert_synthesis.py \
  || fail "missing synthesize_soc_guidance"
echo "OK: synthesis contracts present"

section "2. Live Alpha-Win TH-0003 guidance"
docker exec -i mssp-backend-api python3 - <<'PY' || fail "guidance check failed"
from app.api.routes.alert_incident_triage import _alert_detail
from uuid import UUID
from app.db.session import db_transaction

with db_transaction() as cur:
    cur.execute("""
      SELECT id::text FROM security_alerts
      WHERE tenant_id=(SELECT id FROM tenants WHERE short_code='ALPHAWINCORP-6VS2')
        AND external_alert_id='1785391477.4392428'
    """)
    row = cur.fetchone()
assert row, "reference alert missing"
detail = _alert_detail(UUID(row["id"]))
assert detail.get("asset_criticality"), "missing criticality"
assert detail.get("display_ip_address"), "missing IP"
assert detail.get("display_operating_system"), "missing OS"
assert detail.get("ai_business_impact"), "missing business impact"
assert detail.get("ai_recommended_action"), "missing recommended action"
assert detail.get("ai_likely_attack_type"), "missing attack type"
assert detail.get("device_type") == "windows_host", detail.get("device_type")
print("OK: reference alert fully enriched")
PY


section "3. Final"
echo "VALIDATION PASSED: KB-091 alert enrichment OK"
exit 0
