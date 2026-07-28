#!/usr/bin/env bash
# KB-079: Install automated scan agent + systemd timer on VM 109 (one-time).
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
HOST="${GREENBONE_SSH_HOST:-greenbone}"
KEY_SRC="${VULN_SYNC_API_KEY_FILE:-$PROJECT_DIR/.secrets/vuln_sync_api_key}"

[ -f "$KEY_SRC" ] || { echo "Missing $KEY_SRC on control plane" >&2; exit 1; }

scp -o BatchMode=yes "$PROJECT_DIR/scripts/kb079_vuln_scan_agent.py" \
  "$HOST:/tmp/kb079_vuln_scan_agent.py"
scp -o BatchMode=yes "$PROJECT_DIR/deploy/systemd/mssp-vuln-scan-agent.service" \
  "$PROJECT_DIR/deploy/systemd/mssp-vuln-scan-agent.timer" \
  "$HOST:/tmp/"

ssh -o BatchMode=yes "$HOST" 'sudo bash -s' <<REMOTE
set -euo pipefail
install -d -m 0750 /opt/mssp-vuln-free/bin /opt/mssp-vuln-free/secrets
install -m 0755 /tmp/kb079_vuln_scan_agent.py /opt/mssp-vuln-free/bin/kb079_vuln_scan_agent.py
install -m 0640 /tmp/mssp-vuln-scan-agent.service /etc/systemd/system/mssp-vuln-scan-agent.service
install -m 0640 /tmp/mssp-vuln-scan-agent.timer /etc/systemd/system/mssp-vuln-scan-agent.timer
REMOTE

scp -o BatchMode=yes "$KEY_SRC" "$HOST:/tmp/vuln_sync_api_key"
ssh -o BatchMode=yes "$HOST" 'sudo bash -s' <<'REMOTE'
set -euo pipefail
install -m 0600 /tmp/vuln_sync_api_key /opt/mssp-vuln-free/secrets/vuln_sync_api_key
rm -f /tmp/vuln_sync_api_key
systemctl daemon-reload
systemctl enable --now mssp-vuln-scan-agent.timer
systemctl start mssp-vuln-scan-agent.service || true
systemctl status mssp-vuln-scan-agent.timer --no-pager || true
REMOTE

echo "KB-079: VM 109 scan agent installed (timer every 15 minutes)."
