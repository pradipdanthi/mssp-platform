#!/usr/bin/env bash
# Enroll Linux Velociraptor client on VM 105 → server VM 110.
# Windows VM 104: packs installer under deploy/velociraptor-client/ (manual; no SSH).
set -euo pipefail
SERVER="${VR_SERVER:-192.168.0.220}"
CLIENT="${VR_CLIENT:-192.168.0.215}"
SKEY="${VR_SERVER_KEY:-$HOME/.ssh/id_ed25519_velociraptor}"
CKEY="${VR_CLIENT_KEY:-$HOME/.ssh/id_ed25519_linux_endpoint}"
VER=0.77.1
URL="https://github.com/Velocidex/velociraptor/releases/download/v${VER}/velociraptor-v${VER}-linux-amd64"

ssh -i "$SKEY" -o BatchMode=yes "secadmin@${SERVER}" "sudo bash -s" <<EOF
set -euo pipefail
ROOT=/opt/mssp-velociraptor
CFG=/etc/velociraptor/server.config.yaml
mkdir -p \$ROOT/clients
if [ ! -f \$ROOT/clients/client.config.yaml ]; then
  \$ROOT/bin/velociraptor --config "\$CFG" config client > \$ROOT/clients/client.config.yaml
fi
sed -i 's#https://localhost#https://${SERVER}#g; s#wss://localhost#wss://${SERVER}#g; s#127.0.0.1#${SERVER}#g' \$ROOT/clients/client.config.yaml || true
chmod 0640 \$ROOT/clients/client.config.yaml
EOF

ssh -i "$SKEY" -o BatchMode=yes "secadmin@${SERVER}" \
  'sudo cat /opt/mssp-velociraptor/clients/client.config.yaml' > /tmp/vr-client.config.yaml
sed -i "s#https://localhost#https://${SERVER}#g; s#wss://localhost#wss://${SERVER}#g; s#127.0.0.1#${SERVER}#g" /tmp/vr-client.config.yaml || true

scp -i "$CKEY" -o BatchMode=yes /tmp/vr-client.config.yaml "secadmin@${CLIENT}:/tmp/client.config.yaml"

ssh -i "$CKEY" -o BatchMode=yes "secadmin@${CLIENT}" "sudo bash -s" <<EOF
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl
mkdir -p /opt/mssp-velociraptor-client /etc/velociraptor
if [ ! -x /opt/mssp-velociraptor-client/velociraptor ]; then
  curl -fsSL "$URL" -o /opt/mssp-velociraptor-client/velociraptor
  chmod 0755 /opt/mssp-velociraptor-client/velociraptor
fi
install -m 0640 /tmp/client.config.yaml /etc/velociraptor/client.config.yaml
cat > /etc/systemd/system/velociraptor-client.service <<'UNIT'
[Unit]
Description=Velociraptor Client (MSSP lab)
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
ExecStart=/opt/mssp-velociraptor-client/velociraptor --config /etc/velociraptor/client.config.yaml client -v
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now velociraptor-client
sleep 1
systemctl is-active velociraptor-client
hostname
EOF

mkdir -p /opt/mssp-control/deploy/velociraptor-client
cp /tmp/vr-client.config.yaml /opt/mssp-control/deploy/velociraptor-client/client.config.yaml
cat > /opt/mssp-control/deploy/velociraptor-client/Install-WindowsClient.ps1 <<'PS'
# Run as Administrator on Windows lab VM 104.
$ErrorActionPreference = "Stop"
$Root = "C:\Program Files\MSSP\Velociraptor"
New-Item -ItemType Directory -Force -Path $Root | Out-Null
$Cfg = Join-Path $Root "client.config.yaml"
Copy-Item -Force "$PSScriptRoot\client.config.yaml" $Cfg
$Bin = Join-Path $Root "velociraptor.exe"
if (-not (Test-Path $Bin)) {
  Write-Host "Download Velociraptor Windows amd64 release into $Bin then re-run."
  Write-Host "https://github.com/Velocidex/velociraptor/releases"
  exit 1
}
& sc.exe create VelociraptorClient binPath= "`"$Bin`" --config `"$Cfg`" client -v" start= auto
& sc.exe start VelociraptorClient
Write-Host "Velociraptor client service started"
PS
echo "Linux client enrolled on $CLIENT; Windows installer pack in deploy/velociraptor-client/"
