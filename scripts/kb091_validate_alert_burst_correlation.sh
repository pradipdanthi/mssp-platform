#!/usr/bin/env bash
# KB-091 Phase-1: alert noise suppress + incident burst correlation.
set -euo pipefail
cd /opt/mssp-control

fail() { echo "VALIDATION FAILED: $1" >&2; exit 1; }
section() { echo; echo "---- $1 ----"; }

section "1. Code contracts"
grep -q 'is_known_noise_file_drop' backend-api/app/api/routes/soc_sync.py \
  || fail "missing is_known_noise_file_drop"
grep -q '__psscriptpolicytest_' backend-api/app/api/routes/soc_sync.py \
  || fail "missing PSScriptPolicyTest suppress marker"
grep -q '_create_or_correlate_incident' backend-api/app/services/soc_sync_service.py \
  || fail "missing correlation helper"
grep -q 'SOC_INCIDENT_CORRELATE_MINUTES' backend-api/app/services/soc_sync_service.py \
  || fail "missing correlate window env"
grep -q 'Correlated alert attached' backend-api/app/services/soc_sync_service.py \
  || fail "missing correlate timeline note"
grep -q 'soc-correlate:' backend-api/app/services/soc_sync_service.py \
  || fail "missing correlate advisory lock"
echo "OK: suppress + correlate present"

section "2. Unit checks in API container"
docker exec -i mssp-backend-api python3 - <<'PY' || fail "unit checks failed"
from app.api.routes.soc_sync import is_known_noise_file_drop, _normalize_wazuh_alert

noise = {
  "rule": {"id": "92213", "level": 15, "description": "Executable file dropped in folder commonly used by malware"},
  "agent": {"id": "006", "name": "WIN-BL72S84GDTF", "groups": ["tenant_ALPHAWINCORP_6VS2"]},
  "id": "noise-1",
  "data": {"win": {"eventdata": {"targetFilename": r"C:\Users\Administrator\AppData\Local\Temp\2\__PSScriptPolicyTest_abc.ps1"}}},
}
assert is_known_noise_file_drop(noise) is True
# May fail tenant resolve without DB binding — only test noise flag path via helper
assert is_known_noise_file_drop({
  "data": {"win": {"eventdata": {"targetFilename": r"C:\Temp\malware.exe"}}}
}) is False

from app.services.soc_sync_service import CORRELATE_WINDOW_MINUTES, _should_create_incident
from app.schemas.soc_sync import SocSyncRequest
assert CORRELATE_WINDOW_MINUTES >= 1
p = SocSyncRequest(
  source_tool="wazuh",
  external_alert_id="x",
  severity="critical",
  alert_title="t",
  tenant_short_code="ALPHAWINCORP-6VS2",
  create_incident=False,
)
assert _should_create_incident(p) is False
print("OK: noise detect + create_incident=False honored")
PY

section "3. Final"
echo "VALIDATION PASSED: Phase-1 suppress + correlate contracts OK"
exit 0
