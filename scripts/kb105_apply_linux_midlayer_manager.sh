#!/usr/bin/env bash
# Drop Linux execve high-signal rules (110001-110019) onto the Wazuh Manager.
# Lab default: VM 101. Cloud: set WAZUH_MANAGER_HOST / WAZUH_SSH_KEY / WAZUH_SSH_USER.
# Also appends Linux agent.conf localfile (does not replace Windows mssp-edr-ar-sync).
# Does not change integratord, source_tool, or listen ports.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/deploy/wazuh-manager/mssp_linux_exec_rules.xml"
HELPER="$ROOT/backend-api/app/endpoint_configs/linux-edr-telemetry/install-mssp-linux-telemetry.sh"
WAZUH_HOST="${WAZUH_MANAGER_HOST:-192.168.0.211}"
KEY="${WAZUH_SSH_KEY:-/home/secadmin/.ssh/id_ed25519_wazuh_stack}"
SSH_USER="${WAZUH_SSH_USER:-secadmin}"

[[ -f "$SRC" ]] || { echo "FAIL: missing $SRC" >&2; exit 1; }
[[ -f "$HELPER" ]] || { echo "FAIL: missing $HELPER" >&2; exit 1; }
[[ -f "$KEY" ]] || { echo "FAIL: missing SSH key $KEY" >&2; exit 1; }

SSH=(ssh -T -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=3 "${SSH_USER}@${WAZUH_HOST}")
SCP=(scp -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)

echo "==> Copy Linux execve rules + helper to ${WAZUH_HOST}"
"${SCP[@]}" "$SRC" "$HELPER" "${SSH_USER}@${WAZUH_HOST}:/tmp/"

timeout 90 "${SSH[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
sudo install -d -o wazuh -g wazuh -m 0750 /var/ossec/etc/rules
sudo install -o wazuh -g wazuh -m 0640 /tmp/mssp_linux_exec_rules.xml /var/ossec/etc/rules/mssp_linux_exec_rules.xml
sudo grep -q 'rule id="110001"' /var/ossec/etc/rules/mssp_linux_exec_rules.xml
# Shared helper + localfile so already-enrolled Linux agents pick it up.
# Must use sudo test: secadmin cannot stat /var/ossec/etc/shared/default.
if sudo test -d /var/ossec/etc/shared/default; then
  sudo install -o wazuh -g wazuh -m 0640 /tmp/install-mssp-linux-telemetry.sh \
    /var/ossec/etc/shared/default/install-mssp-linux-telemetry.sh
  if ! sudo grep -q 'mssp-linux-exec-localfile' /var/ossec/etc/shared/default/agent.conf 2>/dev/null; then
    sudo tee -a /var/ossec/etc/shared/default/agent.conf >/dev/null <<'EOF'

<agent_config os="linux">
  <!-- mssp-linux-exec-localfile -->
  <localfile>
    <log_format>audit</log_format>
    <location>/var/log/audit/audit.log</location>
  </localfile>
  <wodle name="command">
    <disabled>no</disabled>
    <tag>mssp-linux-exec-sync</tag>
    <interval>60m</interval>
    <run_on_start>yes</run_on_start>
    <timeout>120</timeout>
    <ignore_output>yes</ignore_output>
    <command>bash /var/ossec/etc/shared/install-mssp-linux-telemetry.sh</command>
  </wodle>
</agent_config>
EOF
    sudo chown wazuh:wazuh /var/ossec/etc/shared/default/agent.conf || true
  fi
fi
sudo timeout 15 /var/ossec/bin/wazuh-control restart >/tmp/mssp-kb105-wazuh-restart.log 2>&1
sleep 3
sudo test -f /var/ossec/etc/rules/mssp_linux_exec_rules.xml
sudo grep -q 'rule id="110001"' /var/ossec/etc/rules/mssp_linux_exec_rules.xml
echo LINUX_MIDLAYER_MANAGER_OK
REMOTE

echo "PASS: Linux execve Manager rules applied on ${WAZUH_HOST}"
