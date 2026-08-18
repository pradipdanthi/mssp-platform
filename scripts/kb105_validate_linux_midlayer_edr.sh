#!/usr/bin/env bash
# Validate Linux mid-layer execve packaging + Windows offline Sysmon fallback.
# Does not install packages on VM 100. Does not change source_tool or AR scripts.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
pass=0; fail=0
ok(){ echo "PASS: $1"; pass=$((pass+1)); }
bad(){ echo "FAIL: $1"; fail=$((fail+1)); }

need_file() {
  local p="$1"
  [[ -f "$p" ]] && ok "file ${p#"$ROOT"/}" || bad "missing ${p#"$ROOT"/}"
}

need_file backend-api/app/endpoint_configs/linux-edr-telemetry/mssp-exec.rules
need_file backend-api/app/endpoint_configs/linux-edr-telemetry/install-mssp-linux-telemetry.sh
need_file deploy/wazuh-manager/mssp_linux_exec_rules.xml
need_file backend-api/app/endpoint_configs/Enable-MsspWindowsTelemetry.ps1
need_file scripts/Enable-MsspWindowsTelemetry.ps1
need_file scripts/bootstrap_windows_telemetry.ps1
need_file scripts/cache_sysmon_offline.sh
need_file scripts/verify_e2e_midlayer_edr.py
need_file ansible/playbooks/mssp-linux-midlayer-manager.yml
need_file ansible/roles/mssp_linux_midlayer/tasks/main.yml
need_file ansible/roles/mssp_linux_midlayer/files/mssp_linux_exec_rules.xml
need_file ansible/roles/mssp_linux_midlayer/files/install-mssp-linux-telemetry.sh

cmp -s deploy/wazuh-manager/mssp_linux_exec_rules.xml \
  ansible/roles/mssp_linux_midlayer/files/mssp_linux_exec_rules.xml \
  && ok "Ansible Manager XML matches deploy canonical" \
  || bad "Ansible mssp_linux_exec_rules.xml drifted from deploy/"
cmp -s backend-api/app/endpoint_configs/linux-edr-telemetry/install-mssp-linux-telemetry.sh \
  ansible/roles/mssp_linux_midlayer/files/install-mssp-linux-telemetry.sh \
  && ok "Ansible Linux helper matches endpoint_configs canonical" \
  || bad "Ansible install-mssp-linux-telemetry.sh drifted from backend-api/"
grep -q 'sudo test -d /var/ossec/etc/shared/default' scripts/kb105_apply_linux_midlayer_manager.sh \
  && ok "lab apply uses sudo test for shared/default" \
  || bad "apply script must sudo test shared/default (secadmin cannot stat it)"
grep -q 'mssp-linux-exec-localfile' scripts/kb105_apply_linux_midlayer_manager.sh \
  && ok "lab apply script appends Linux agent.conf localfile" \
  || bad "apply script missing Linux agent.conf"
grep -q 'cache_sysmon_offline' scripts/production_deploy_control_plane.sh \
  && ok "control-plane deploy caches Sysmon before image build" \
  || bad "production_deploy_control_plane.sh missing Sysmon cache"
grep -q 'mssp-linux-midlayer-manager' scripts/production_deploy_engines.sh \
  && ok "engine deploy order includes Linux mid-layer playbook" \
  || bad "production_deploy_engines.sh missing mid-layer playbook"

grep -q 'key=mssp_exec' backend-api/app/endpoint_configs/linux-edr-telemetry/mssp-exec.rules \
  && ok "auditd execve key=mssp_exec" || bad "auditd key"
grep -q 'execve,execveat' backend-api/app/endpoint_configs/linux-edr-telemetry/mssp-exec.rules \
  && ok "auditd watches execve/execveat" || bad "auditd syscalls"
grep -q '/var/log/audit/audit.log' backend-api/app/endpoint_configs/linux-edr-telemetry/install-mssp-linux-telemetry.sh \
  && ok "installer wires audit.log localfile" || bad "ossec localfile path"
grep -q '<log_format>audit</log_format>' backend-api/app/endpoint_configs/linux-edr-telemetry/install-mssp-linux-telemetry.sh \
  && ok "Wazuh log_format=audit (endpoint_audit_exec)" || bad "log_format audit"
grep -q 'MSSP_LINUX_TELEMETRY_OK' backend-api/app/endpoint_configs/linux-edr-telemetry/install-mssp-linux-telemetry.sh \
  && ok "linux telemetry success marker" || bad "success marker"

grep -q '_linux_midlayer_suffix' backend-api/app/services/agent_package_builder.py \
  && ok "package builder appends linux mid-layer" || bad "builder mid-layer"
grep -q 'install-mssp-linux-telemetry.sh' backend-api/app/services/agent_package_builder.py \
  && ok "ZIP includes linux telemetry helper" || bad "ZIP helper"
grep -q 'resolve_sysmon_binary' backend-api/app/services/agent_package_builder.py \
  && ok "ZIP can embed Sysmon64.exe" || bad "sysmon embed helper"
grep -q 'auditd execve' backend-api/app/services/agent_install_repo.py \
  && ok "one-liner documents auditd execve" || bad "install repo comment"

grep -q 'rule id="110001"' deploy/wazuh-manager/mssp_linux_exec_rules.xml \
  && ok "Manager high-signal rule 110001" || bad "rule 110001"
grep -q 'rule id="110005"' deploy/wazuh-manager/mssp_linux_exec_rules.xml \
  && ok "Manager high-signal rule 110005" || bad "rule 110005"
if grep -qE 'rule id="(92057|92213|100049)"' deploy/wazuh-manager/mssp_linux_exec_rules.xml; then
  bad "new rules must not reuse 92057/92213/100049"
else
  ok "reserved rule IDs not reused"
fi

grep -q 'Resolve-BundledSysmonBinary' backend-api/app/endpoint_configs/Enable-MsspWindowsTelemetry.ps1 \
  && ok "Windows local Sysmon64.exe first" || bad "bundled sysmon resolver"
grep -q 'download.sysinternals.com' backend-api/app/endpoint_configs/Enable-MsspWindowsTelemetry.ps1 \
  && ok "Sysinternals download is fallback" || bad "sysinternals fallback"

# Do not alter Windows AR scripts in this change.
for f in mssp-isolate-host mssp-kill-process mssp-block-hash; do
  [[ -f "deploy/wazuh-active-response/$f" ]] && ok "linux AR present: $f" || bad "missing AR $f"
done

grep -q '_publish_linux_midlayer_shared' kevantic-appliance/cli/kevantic-cli/kevantic_cli/register_ops.py \
  && ok "appliance CLI publishes linux mid-layer" || bad "register_ops linux publish"
grep -q 'mssp-edr-ar-sync' kevantic-appliance/cli/kevantic-cli/kevantic_cli/register_ops.py \
  && ok "Windows shared agent.conf marker preserved" || bad "windows agent.conf marker"

if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
  docker compose exec -T backend-api python - <<'PY' && ok "linux ZIP embeds auditd helper" || bad "linux ZIP embed"
from app.services.agent_package_builder import build_agent_package_zip, build_linux_install_script
import zipfile, io
data, name = build_agent_package_zip(
    tenant_name="T", short_code="TESTLNX", wazuh_agent_group="tenant_TESTLNX", os_type="linux"
)
z = zipfile.ZipFile(io.BytesIO(data))
names = set(z.namelist())
need = {
    "linux/install-linux-agent.sh",
    "linux/install-mssp-linux-telemetry.sh",
    "linux/mssp-exec.rules",
}
missing = need - names
assert not missing, missing
script = z.read("linux/install-linux-agent.sh").decode()
assert "install-mssp-linux-telemetry.sh" in script
assert "audit.log" in script or "MSSP_LINUX_TELEMETRY" in script
one = build_linux_install_script(short_code="TESTLNX", wazuh_agent_group="tenant_TESTLNX")
assert "auditd" in one or "mssp_exec" in one or "MSSP_LINUX_TELEMETRY" in one
print("linux_zip_ok", name)
PY
else
  echo "SKIP: backend-api not running (ZIP embed check)"
fi

echo "----"
echo "KB-105 linux mid-layer EDR: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
