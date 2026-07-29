#!/usr/bin/env bash
# Validate Windows telemetry bootstrap is wired into packages + scripts.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
pass=0; fail=0
ok(){ echo "PASS: $1"; pass=$((pass+1)); }
bad(){ echo "FAIL: $1"; fail=$((fail+1)); }

test -f scripts/bootstrap_windows_telemetry.ps1 && ok "bootstrap_windows_telemetry.ps1" || bad "bootstrap script"
test -f scripts/sysmon-windows-baseline.xml && ok "scripts/sysmon baseline" || bad "scripts sysmon xml"
test -f backend-api/app/endpoint_configs/Enable-MsspWindowsTelemetry.ps1 && ok "API endpoint_configs telemetry ps1" || bad "API ps1"
test -f backend-api/app/endpoint_configs/sysmon-windows-baseline.xml && ok "API sysmon xml" || bad "API sysmon"
grep -q 'Enable-MsspWindowsTelemetry' backend-api/app/services/agent_package_builder.py && ok "package builder calls telemetry" || bad "package builder"
grep -q 'Microsoft-Windows-Sysmon/Operational' scripts/bootstrap_windows_telemetry.ps1 && ok "bootstrap wires Sysmon channel" || bad "sysmon localfile"
grep -q 'EventID=4688' scripts/bootstrap_windows_telemetry.ps1 && ok "bootstrap wires 4688" || bad "4688 localfile"
grep -q 'ProcessCreationIncludeCmdLine_Enabled' scripts/bootstrap_windows_telemetry.ps1 && ok "bootstrap enables cmdline audit" || bad "cmdline audit"

if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
  docker compose exec -T backend-api python - <<'PY' && ok "builder embeds telemetry files" || bad "builder embed check"
from app.services.agent_package_builder import build_agent_package_zip
import zipfile, io
data, name = build_agent_package_zip(
    tenant_name="T", short_code="TESTWIN", wazuh_agent_group="tenant_TESTWIN", os_type="windows"
)
z = zipfile.ZipFile(io.BytesIO(data))
names = set(z.namelist())
need = {
    "windows/install-windows-agent.ps1",
    "windows/Enable-MsspWindowsTelemetry.ps1",
    "windows/sysmon-windows-baseline.xml",
}
missing = need - names
assert not missing, missing
script = z.read("windows/install-windows-agent.ps1").decode()
assert "Enable-MsspWindowsTelemetry.ps1" in script
print("zip_ok", name)
PY
fi

echo "----"
echo "KB-088 windows telemetry: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
