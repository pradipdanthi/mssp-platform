#!/usr/bin/env bash
# Deploy MSSP EDR Active Response scripts to Wazuh manager + Linux lab agent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/deploy/wazuh-active-response"
WAZUH_HOST="${WAZUH_MANAGER_HOST:-192.168.0.211}"
LINUX_AGENT_HOST="${WAZUH_LINUX_AGENT_HOST:-192.168.0.215}"
KEY="${WAZUH_SSH_KEY:-/home/secadmin/.ssh/id_ed25519_wazuh_stack}"
LINUX_KEY="${WAZUH_LINUX_SSH_KEY:-/home/secadmin/.ssh/id_ed25519_linux_endpoint}"
SSH_USER="${WAZUH_SSH_USER:-secadmin}"

for f in mssp-isolate-host mssp-kill-process mssp-block-hash; do
  [[ -f "$SRC/$f" ]] || { echo "FAIL: missing $SRC/$f"; exit 1; }
done

install_scripts() {
  local host="$1" key="$2"
  echo ">> Installing AR scripts on $host"
  scp -i "$key" -o StrictHostKeyChecking=accept-new \
    "$SRC/mssp-isolate-host" "$SRC/mssp-kill-process" "$SRC/mssp-block-hash" \
    "${SSH_USER}@${host}:/tmp/"
  ssh -i "$key" -o StrictHostKeyChecking=accept-new "${SSH_USER}@${host}" \
    'for f in mssp-isolate-host mssp-kill-process mssp-block-hash; do
       sudo install -o root -g wazuh -m 0750 "/tmp/$f" "/var/ossec/active-response/bin/$f"
       rm -f "/tmp/$f"
     done
     ls -la /var/ossec/active-response/bin/mssp-*'
}

install_scripts "$WAZUH_HOST" "$KEY"
install_scripts "$LINUX_AGENT_HOST" "$LINUX_KEY"

echo ">> Registering AR commands on manager"
ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "${SSH_USER}@${WAZUH_HOST}" 'bash -s' <<'REMOTE'
set -euo pipefail
CONF=/var/ossec/etc/ossec.conf
if sudo grep -q '<name>mssp-isolate-host</name>' "$CONF"; then
  echo "commands already registered"
else
  sudo cp -a "$CONF" "${CONF}.bak.mssp-edr.$(date +%Y%m%d%H%M%S)"
  sudo python3 <<'PY'
from pathlib import Path
conf = Path("/var/ossec/etc/ossec.conf")
text = conf.read_text(encoding="utf-8")
block = """
  <!-- MSSP EDR Active Response (KB-083) -->
  <command>
    <name>mssp-isolate-host</name>
    <executable>mssp-isolate-host</executable>
    <timeout_allowed>yes</timeout_allowed>
  </command>
  <command>
    <name>mssp-kill-process</name>
    <executable>mssp-kill-process</executable>
  </command>
  <command>
    <name>mssp-block-hash</name>
    <executable>mssp-block-hash</executable>
  </command>
"""
marker = "</ossec_config>"
idx = text.rfind(marker)
if idx < 0:
    raise SystemExit("ossec.conf missing </ossec_config>")
conf.write_text(text[:idx] + block + "\n" + text[idx:], encoding="utf-8")
print("commands registered")
PY
fi
sudo /var/ossec/bin/wazuh-control restart
sleep 4
sudo /var/ossec/bin/wazuh-control status | head -15
REMOTE

echo "PASS: MSSP AR scripts deployed (manager + linux agent)"
