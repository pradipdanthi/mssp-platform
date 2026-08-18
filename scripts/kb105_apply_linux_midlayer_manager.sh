#!/usr/bin/env bash
# Drop Linux execve high-signal rules (110001-110019) onto Wazuh Manager VM 101.
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

SSH=(ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${SSH_USER}@${WAZUH_HOST}")
SCP=(scp -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)

echo "==> Copy Linux execve rules + helper to ${WAZUH_HOST}"
"${SCP[@]}" "$SRC" "$HELPER" "${SSH_USER}@${WAZUH_HOST}:/tmp/"

"${SSH[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
sudo install -d -o wazuh -g wazuh -m 0750 /var/ossec/etc/rules
sudo install -o wazuh -g wazuh -m 0640 /tmp/mssp_linux_exec_rules.xml /var/ossec/etc/rules/mssp_linux_exec_rules.xml
sudo grep -q 'rule id="110001"' /var/ossec/etc/rules/mssp_linux_exec_rules.xml
# Shared helper so already-enrolled Linux agents can pick it up from default group.
if [[ -d /var/ossec/etc/shared/default ]]; then
  sudo install -o wazuh -g wazuh -m 0640 /tmp/install-mssp-linux-telemetry.sh \
    /var/ossec/etc/shared/default/install-mssp-linux-telemetry.sh
fi
sudo timeout 15 /var/ossec/bin/wazuh-control restart
sleep 3
sudo timeout 10 /var/ossec/bin/wazuh-control status | head -15 || true
sudo test -f /var/ossec/etc/rules/mssp_linux_exec_rules.xml
sudo grep -q 'rule id="110001"' /var/ossec/etc/rules/mssp_linux_exec_rules.xml
echo LINUX_MIDLAYER_MANAGER_OK
REMOTE

echo "PASS: Linux execve Manager rules applied on ${WAZUH_HOST}"
