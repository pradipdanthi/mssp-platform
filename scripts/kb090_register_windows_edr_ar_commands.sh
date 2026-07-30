#!/usr/bin/env bash
# Register Windows EDR AR command names on Wazuh Manager (once).
# Does not touch endpoints — pair with Install-MsspWindowsEdrAr.ps1 on Windows hosts.
set -euo pipefail

WAZUH_HOST="${WAZUH_MANAGER_HOST:-192.168.0.211}"
KEY="${WAZUH_SSH_KEY:-/home/secadmin/.ssh/id_ed25519_wazuh_stack}"
SSH_USER="${WAZUH_SSH_USER:-secadmin}"

echo ">> Registering Windows AR commands on $WAZUH_HOST"
ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "${SSH_USER}@${WAZUH_HOST}" 'bash -s' <<'REMOTE'
set -euo pipefail
CONF=/var/ossec/etc/ossec.conf
if sudo grep -q '<name>mssp-kill-process.cmd</name>' "$CONF"; then
  echo "Windows AR commands already registered"
else
  sudo cp -a "$CONF" "${CONF}.bak.mssp-edr-win.$(date +%Y%m%d%H%M%S)"
  sudo python3 <<'PY'
from pathlib import Path
conf = Path("/var/ossec/etc/ossec.conf")
text = conf.read_text(encoding="utf-8")
block = """
  <!-- MSSP EDR Active Response Windows (KB-090) -->
  <command>
    <name>mssp-isolate-host.cmd</name>
    <executable>mssp-isolate-host.cmd</executable>
    <timeout_allowed>no</timeout_allowed>
  </command>
  <command>
    <name>mssp-kill-process.cmd</name>
    <executable>mssp-kill-process.cmd</executable>
    <timeout_allowed>no</timeout_allowed>
  </command>
  <command>
    <name>mssp-block-hash.cmd</name>
    <executable>mssp-block-hash.cmd</executable>
    <timeout_allowed>no</timeout_allowed>
  </command>
"""
marker = "</ossec_config>"
idx = text.rfind(marker)
if idx < 0:
    raise SystemExit("ossec.conf missing </ossec_config>")
conf.write_text(text[:idx] + block + "\n" + text[idx:], encoding="utf-8")
print("Windows AR commands registered")
PY
  sudo /var/ossec/bin/wazuh-control restart
  sleep 4
fi
sudo grep -n 'mssp-.*\.cmd' /var/ossec/etc/ossec.conf || true
sudo /var/ossec/bin/wazuh-control status | head -12
REMOTE

echo "PASS: Windows AR commands present on Manager"
