#!/usr/bin/env bash
# Direct install of Velociraptor + MSSP bridge on VM 110 (when Ansible host keys lag).
set -euo pipefail
HOST="${VELO_HOST:-192.168.0.220}"
KEY="${VELO_SSH_KEY:-$HOME/.ssh/id_ed25519_velociraptor}"
ROOT=/opt/mssp-velociraptor
VER=0.77.1
URL="https://github.com/Velocidex/velociraptor/releases/download/v${VER}/velociraptor-v${VER}-linux-amd64"

ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o BatchMode=yes "secadmin@${HOST}" "sudo bash -s" <<EOF
set -euo pipefail
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ca-certificates curl openssl python3 jq
mkdir -p $ROOT/{bin,secrets,clients,artifacts} /etc/velociraptor /var/lib/mssp/velociraptor
if [ ! -x $ROOT/bin/velociraptor ]; then
  curl -fsSL "$URL" -o $ROOT/bin/velociraptor
  chmod 0755 $ROOT/bin/velociraptor
fi
if [ ! -f /etc/velociraptor/server.config.yaml ]; then
  $ROOT/bin/velociraptor config generate > /etc/velociraptor/server.config.yaml
  sed -i 's/bind_address: 127.0.0.1/bind_address: 0.0.0.0/g' /etc/velociraptor/server.config.yaml || true
fi
if [ ! -s $ROOT/secrets/bridge_api_key ]; then
  openssl rand -hex 32 > $ROOT/secrets/bridge_api_key
  chmod 0600 $ROOT/secrets/bridge_api_key
fi
cat > /etc/systemd/system/velociraptor.service <<'UNIT'
[Unit]
Description=Velociraptor DFIR Server
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
ExecStart=/opt/mssp-velociraptor/bin/velociraptor --config /etc/velociraptor/server.config.yaml frontend -v
Restart=on-failure
RestartSec=5
LimitNOFILE=65535
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/mssp-velociraptor-bridge.service <<'UNIT'
[Unit]
Description=MSSP Velociraptor bridge
After=network-online.target velociraptor.service
[Service]
Type=simple
Environment=VR_BIN=/opt/mssp-velociraptor/bin/velociraptor
Environment=VR_CONFIG=/etc/velociraptor/server.config.yaml
Environment=BRIDGE_API_KEY_FILE=/opt/mssp-velociraptor/secrets/bridge_api_key
Environment=BRIDGE_BIND=0.0.0.0
Environment=BRIDGE_PORT=8001
Environment=ARTIFACT_STORE=/opt/mssp-velociraptor/artifacts
ExecStart=/usr/bin/python3 /opt/mssp-velociraptor/bin/mssp_velociraptor_bridge.py
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
echo installed > /var/lib/mssp/velociraptor/installed
systemctl daemon-reload
systemctl enable --now velociraptor
EOF

scp -i "$KEY" -o BatchMode=yes \
  /opt/mssp-control/ansible/roles/velociraptor/files/mssp_velociraptor_bridge.py \
  "secadmin@${HOST}:/tmp/mssp_velociraptor_bridge.py"
ssh -i "$KEY" -o BatchMode=yes "secadmin@${HOST}" \
  'sudo install -m 0755 /tmp/mssp_velociraptor_bridge.py /opt/mssp-velociraptor/bin/mssp_velociraptor_bridge.py && sudo systemctl enable --now mssp-velociraptor-bridge && sleep 1 && curl -fsS http://127.0.0.1:8001/health && echo && sudo cat /opt/mssp-velociraptor/secrets/bridge_api_key | wc -c'

echo "Install complete on $HOST"
