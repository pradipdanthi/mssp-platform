#!/usr/bin/env bash
# Validate Windows EDR AR is packaged for day-one Windows agent downloads.
set -euo pipefail
cd /opt/mssp-control

fail() { echo "VALIDATION FAILED: $1" >&2; exit 1; }
section() { echo; echo "----------------------------------------------------------------------"; echo "$1"; echo "----------------------------------------------------------------------"; }

section "1. Windows AR source files exist"
for f in \
  deploy/wazuh-active-response/windows/mssp-kill-process.cmd \
  deploy/wazuh-active-response/windows/mssp-kill-process.ps1 \
  deploy/wazuh-active-response/windows/mssp-isolate-host.cmd \
  deploy/wazuh-active-response/windows/mssp-isolate-host.ps1 \
  deploy/wazuh-active-response/windows/mssp-block-hash.cmd \
  deploy/wazuh-active-response/windows/mssp-block-hash.ps1 \
  deploy/wazuh-active-response/windows/Install-MsspWindowsEdrAr.ps1 \
  deploy/wazuh-active-response/windows/Sync-MsspEdrAr.ps1 \
  deploy/wazuh-active-response/windows/Watch-MsspQuarantine.ps1
do
  [ -f "$f" ] || fail "missing $f"
  # PowerShell on Windows can choke on UTF-8 punctuation in scripts we ship.
  python3 -c "import pathlib; d=pathlib.Path('$f').read_bytes(); assert sum(b>127 for b in d)==0, 'non-ascii'" \
    || fail "$f contains non-ASCII bytes"
  echo "OK: $f"
done

section "2. Package builder embeds edr-ar/"
grep -q 'load_windows_edr_ar_files' backend-api/app/services/agent_package_builder.py \
  || fail "package builder missing load_windows_edr_ar_files"
grep -q 'windows/edr-ar/' backend-api/app/services/agent_package_builder.py \
  || fail "package builder missing windows/edr-ar/ zip paths"
grep -q 'Install-MsspWindowsEdrAr.ps1' backend-api/app/services/agent_package_builder.py \
  || fail "windows installer must call Install-MsspWindowsEdrAr.ps1"
grep -q 'mssp-kill-process.cmd' backend-api/app/services/edr_actions.py \
  || fail "edr_actions WIN kill default must be mssp-kill-process.cmd"
grep -q 'EDR_ISOLATE_SECONDS") or "0"' backend-api/app/services/edr_actions.py \
  || fail "isolate default must be hold-until-unisolate (0)"
grep -q 'ISOLATE_HOLD_ARG' backend-api/app/services/edr_actions.py \
  || fail "isolate must pass hold token, not a numeric Wazuh timeout"
grep -q 'ignored wazuh timed delete' deploy/wazuh-active-response/windows/mssp-isolate-host.ps1 \
  || fail "Windows isolate must ignore Wazuh timed delete"
grep -q 'Disable-NonMsspOutboundAllows' deploy/wazuh-active-response/windows/mssp-isolate-host.ps1 \
  || fail "Windows isolate must disable existing outbound Allow rules"
grep -q 'sysnative' deploy/wazuh-active-response/windows/mssp-isolate-host.cmd \
  || fail "Windows isolate cmd must launch 64-bit PowerShell"
grep -q '_publish_windows_edr_ar_shared' kevantic-appliance/cli/kevantic-cli/kevantic_cli/register_ops.py \
  || fail "appliance CLI must publish Windows isolate scripts to Manager shared"
grep -q 'hold-until-unisolate' deploy/wazuh-active-response/windows/mssp-isolate-host.ps1 \
  || fail "Windows isolate must hold until Un-isolate"
echo "OK: package + API command defaults"

section "3. Build a sample Windows ZIP and assert AR members"
PYTHONPATH=backend-api python3 - <<'PY' || fail "sample zip build failed"
from app.services.agent_package_builder import build_agent_package_zip
import io, zipfile
data, name = build_agent_package_zip(
    tenant_name="Alpha-Win-Corp",
    short_code="ALPHAWINCORP-6VS2",
    wazuh_agent_group="tenant_ALPHAWINCORP_6VS2",
    os_type="windows",
)
zf = zipfile.ZipFile(io.BytesIO(data))
names = set(zf.namelist())
needed = {
    "windows/edr-ar/mssp-kill-process.cmd",
    "windows/edr-ar/mssp-kill-process.ps1",
    "windows/edr-ar/mssp-isolate-host.cmd",
    "windows/edr-ar/mssp-block-hash.cmd",
    "windows/edr-ar/Install-MsspWindowsEdrAr.ps1",
    "windows/edr-ar/Sync-MsspEdrAr.ps1",
    "windows/edr-ar/Watch-MsspQuarantine.ps1",
    "windows/install-windows-agent.ps1",
}
missing = sorted(needed - names)
assert not missing, missing
script = zf.read("windows/install-windows-agent.ps1").decode("utf-8")
assert "Install-MsspWindowsEdrAr.ps1" in script
cmd = zf.read("windows/edr-ar/mssp-isolate-host.cmd").decode("utf-8")
assert r"%~dp0..\..\shared" in cmd, "isolate cmd must copy Manager shared scripts into bin"
ps1 = zf.read("windows/edr-ar/mssp-isolate-host.ps1").decode("utf-8")
assert "hold-until-unisolate" in ps1
assert "Get-NetFirewallRule -Enabled True" not in ps1
print("OK: zip", name, "contains EDR AR pack")
PY

section "4. Final verdict"
echo "VALIDATION PASSED: Windows kill/isolate/block-hash packaged for day-one downloads."
exit 0
