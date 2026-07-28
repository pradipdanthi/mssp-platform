#!/usr/bin/env bash
# KB-084: validate EDR lifecycle, forensics upload path, process-tree enrichment, onboarding configs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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

check "migration file exists" test -f postgres/init/015_kb084_edr_lifecycle_forensics.sql
check "sysmon template exists" test -f templates/endpoint-configs/sysmon-windows-baseline.xml
check "osquery pack exists" test -f templates/endpoint-configs/osquery-endpoint-pack.conf
check "backend endpoint_configs copied" test -f backend-api/app/endpoint_configs/sysmon-windows-baseline.xml
check "callback route in edr.py" grep -q 'actions/callback' backend-api/app/api/routes/edr.py
check "forensics complete route" grep -q 'forensics/complete' backend-api/app/api/routes/edr.py
check "UNISOLATE in schemas" grep -q 'UNISOLATE_HOST' backend-api/app/schemas/edr.py
check "process normalize service" grep -q 'normalize_process_event' backend-api/app/services/edr_process_tree.py
check "admin onboarding route" grep -q 'agent-configs' backend-api/app/api/routes/admin_onboarding_configs.py
check "main includes onboarding router" grep -q 'admin_onboarding_configs_router' backend-api/app/main.py
check "customer UI unisolate" grep -q 'UNISOLATE_HOST' frontend-customer/src/components/edr/EdrControlPanel.tsx
check "admin UI unisolate" grep -q 'UNISOLATE_HOST' frontend-admin/src/components/edr/EdrControlPanel.tsx
check "customer no Wazuh string in EdrControlPanel" \
  bash -c '! grep -qiE "wazuh|shuffle|sysmon|osquery" frontend-customer/src/components/edr/EdrControlPanel.tsx'
check "customer no engine names in ProcessTreeWidget" \
  bash -c '! grep -qiE "wazuh|shuffle|sysmon|osquery" frontend-customer/src/components/edr/ProcessTreeWidget.tsx'
check "fixture payloads exist" test -f docs/fixtures/kb084_edr_mock_payloads.json

UNIT_PY='
from app.services.edr_process_tree import build_process_forest, normalize_process_event
from app.services import edr_forensics_storage
raw = {"rule":{"groups":["sysmon"],"mitre":[{"id":"T1059.001"}]},"agent":{"id":"001"},"data":{"win":{"eventdata":{"ProcessId":"4242","ParentProcessId":"1000","Image":"C:\\\\Windows\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe","ParentImage":"C:\\\\Windows\\\\explorer.exe","CommandLine":"powershell.exe -enc AAAA","User":"CORP\\\\alice","ProcessGuid":"{guid-child}","ParentProcessGuid":"{guid-parent}","Hashes":"MD5=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,SHA256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}}}}
parent = {"rule":{"groups":["sysmon"]},"data":{"win":{"eventdata":{"ProcessId":"1000","ParentProcessId":"4","Image":"C:\\\\Windows\\\\explorer.exe","ProcessGuid":"{guid-parent}","ParentProcessGuid":"{guid-root}","User":"CORP\\\\alice"}}}}
n = normalize_process_event(raw)
assert n and n["pid"] == 4242 and n["parent_pid"] == 1000, n
assert n["hash_sha256"] and n["process_guid"] == "{guid-child}"
assert build_process_forest([parent, raw]).root is not None
assert normalize_process_event({"rule":{"groups":["audit"]},"data":{"audit":{"pid":"55","ppid":"1","exe":"/usr/bin/curl","command":"curl http://x"}}})["pid"] == 55
assert normalize_process_event({"osquery":[{"pid":9,"parent":1,"name":"sshd","cmdline":"sshd -D","sha256":"c"*64}]})["pid"] == 9
up = edr_forensics_storage.build_upload_url(artifact_id="11111111-1111-1111-1111-111111111111", tenant_id="22222222-2222-2222-2222-222222222222")
token = up["upload_url"].split("token=")[1]
assert edr_forensics_storage.verify_signed_token(token=token, artifact_id="11111111-1111-1111-1111-111111111111", tenant_id="22222222-2222-2222-2222-222222222222", purpose="upload")
key = edr_forensics_storage.object_key_for(tenant_id="22222222-2222-2222-2222-222222222222", endpoint_id="001", artifact_id="11111111-1111-1111-1111-111111111111")
size, sha = edr_forensics_storage.write_upload(object_key=key, body=b"PK\x03\x04mock-zip")
assert size > 0 and len(sha) == 64
print("python_unit_ok")
'

if docker ps --format '{{.Names}}' | grep -qx mssp-backend-api; then
  if docker exec -e JWT_SECRET=kb084-validation-secret-not-for-production \
      -e EDR_FORENSICS_STORAGE_PATH=/tmp/mssp-forensics-kb084 \
      mssp-backend-api python -c "$UNIT_PY"; then
    echo "PASS: python process-tree + forensics unit mocks"
    pass=$((pass + 1))
  else
    echo "FAIL: python process-tree + forensics unit mocks"
    fail=$((fail + 1))
  fi
else
  echo "SKIP: python unit mocks (backend container not running)"
fi

if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
  check "health" curl -fsS http://localhost:8000/health >/dev/null
  check "openapi callback path" \
    bash -c 'curl -fsS http://localhost:8000/openapi.json | grep -q "/v1/edr/actions/callback"'
  check "openapi forensics complete" \
    bash -c 'curl -fsS http://localhost:8000/openapi.json | grep -q "/v1/edr/forensics/complete"'
  check "openapi agent-configs" \
    bash -c 'curl -fsS http://localhost:8000/openapi.json | grep -q "/admin/onboarding/agent-configs"'
  if docker ps --format '{{.Names}}' | grep -qx mssp-postgres; then
    check "db status_detail column" \
      bash -c "docker exec mssp-postgres psql -U mssp_admin -d mssp_control -tAc \"SELECT 1 FROM information_schema.columns WHERE table_name='edr_action_executions' AND column_name='status_detail'\" | grep -q 1"
    check "db edr_forensic_artifacts" \
      bash -c "docker exec mssp-postgres psql -U mssp_admin -d mssp_control -tAc \"SELECT to_regclass('public.edr_forensic_artifacts')\" | grep -q edr_forensic_artifacts"
    check "db edr_process_events" \
      bash -c "docker exec mssp-postgres psql -U mssp_admin -d mssp_control -tAc \"SELECT to_regclass('public.edr_process_events')\" | grep -q edr_process_events"
  fi
else
  echo "SKIP: live API (backend not reachable on :8000)"
fi

echo "----"
echo "KB-084 validation: $pass passed, $fail failed"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
echo "KB-084 PASS"
