#!/usr/bin/env bash
# Install Amass + EASM agent on VM 109 and sync API key to control plane secrets.
set -euo pipefail
HOST="${EASM_HOST:-192.168.0.219}"
KEY="${EASM_SSH_KEY:-$HOME/.ssh/id_ed25519_greenbone}"
ROOT=/opt/mssp-easm-agent
AMASS_VER=4.2.0
AMASS_URL="https://github.com/owasp-amass/amass/releases/download/v${AMASS_VER}/amass_Linux_amd64.zip"

scp -i "$KEY" -o BatchMode=yes \
  /opt/mssp-control/ansible/roles/easm_recon_stack/files/mssp_easm_scan_agent.py \
  "secadmin@${HOST}:/tmp/mssp_easm_scan_agent.py"

ssh -i "$KEY" -o BatchMode=yes "secadmin@${HOST}" "sudo bash -s" <<EOF
set -euo pipefail
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ca-certificates curl unzip jq python3 openssl
mkdir -p $ROOT/{bin,secrets,work} /var/lib/mssp/easm-agent
cd /tmp
curl -fsSL "$AMASS_URL" -o amass.zip
rm -rf /tmp/amass_extract && mkdir -p /tmp/amass_extract
unzip -qo amass.zip -d /tmp/amass_extract
BIN=\$(find /tmp/amass_extract -type f -name amass | head -1)
install -m 0755 "\$BIN" $ROOT/bin/amass
install -m 0755 /tmp/mssp_easm_scan_agent.py $ROOT/bin/mssp_easm_scan_agent.py
if [ ! -s $ROOT/secrets/easm_sync_api_key ]; then
  # Prefer sharing vuln sync key if present for co-located ops
  if [ -s /opt/mssp-vuln-free/secrets/vuln_sync_api_key ]; then
    cp /opt/mssp-vuln-free/secrets/vuln_sync_api_key $ROOT/secrets/easm_sync_api_key
  else
    openssl rand -hex 32 > $ROOT/secrets/easm_sync_api_key
  fi
  chmod 0600 $ROOT/secrets/easm_sync_api_key
fi
cat > /etc/systemd/system/mssp-easm-scan-agent.service <<'UNIT'
[Unit]
Description=MSSP EASM deep recon agent
After=network-online.target
[Service]
Type=oneshot
Environment=CONTROL_PLANE_URL=http://192.168.0.201:8000
Environment=EASM_SYNC_API_KEY_FILE=/opt/mssp-easm-agent/secrets/easm_sync_api_key
Environment=AMASS_BIN=/opt/mssp-easm-agent/bin/amass
Environment=NUCLEI_BIN=/opt/mssp-vuln-free/bin/nuclei
Environment=NUCLEI_TEMPLATES=/opt/mssp-vuln-free/nuclei-templates
Environment=EASM_WORK=/opt/mssp-easm-agent/work
ExecStart=/usr/bin/python3 /opt/mssp-easm-agent/bin/mssp_easm_scan_agent.py
Nice=10
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/mssp-easm-scan-agent.timer <<'UNIT'
[Unit]
Description=Run MSSP EASM recon every 20 minutes
[Timer]
OnBootSec=3min
OnUnitActiveSec=20min
Persistent=true
Unit=mssp-easm-scan-agent.service
[Install]
WantedBy=timers.target
UNIT
echo installed > /var/lib/mssp/easm-agent/installed
systemctl daemon-reload
systemctl enable --now mssp-easm-scan-agent.timer
$ROOT/bin/amass -version || true
systemctl list-timers mssp-easm-scan-agent.timer --no-pager | head -5
EOF

# Pull key to control plane secrets (no print of value)
mkdir -p /opt/mssp-control/.secrets
ssh -i "$KEY" -o BatchMode=yes "secadmin@${HOST}" \
  'sudo cat /opt/mssp-easm-agent/secrets/easm_sync_api_key' \
  > /opt/mssp-control/.secrets/easm_sync_api_key
chmod 600 /opt/mssp-control/.secrets/easm_sync_api_key
# Also ensure vuln key symlink fallback exists if present on CP
echo "EASM agent installed; key stored under .secrets/easm_sync_api_key"
