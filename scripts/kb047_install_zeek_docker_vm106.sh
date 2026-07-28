#!/usr/bin/env bash
# KB-047: Install Zeek on VM 106 via official Docker image (APT mirror blocked).
# Run from control plane; SSH to suricata-sensor.
set -euo pipefail

HOST="${ZEEK_SENSOR_HOST:-192.168.0.216}"
SSH_KEY="${ZEEK_SENSOR_SSH_KEY:-/home/secadmin/.ssh/id_ed25519_suricata}"
ZEEK_IF="${ZEEK_CAPTURE_IF:-enp6s20}"

ssh -i "$SSH_KEY" "secadmin@${HOST}" "bash -s" <<REMOTE
set -euo pipefail
ZEEK_IF="${ZEEK_IF}"

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker secadmin || true
fi

sudo mkdir -p /opt/zeek-logs
sudo chown secadmin:secadmin /opt/zeek-logs

if ! ip link show "\$ZEEK_IF" &>/dev/null; then
  echo "WARNING: \$ZEEK_IF not found. Add Proxmox net2 + mirror, run kb047_configure_zeek_capture_nic_vm106.sh"
  echo "Available interfaces:"
  ip -br link
  exit 1
fi

sudo docker pull zeek/zeek:7.0.7

sudo tee /etc/systemd/system/mssp-zeek-docker.service >/dev/null <<UNIT
[Unit]
Description=MSSP Zeek sensor (Docker)
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
Restart=always
RestartSec=15
ExecStartPre=-/usr/bin/docker rm -f mssp-zeek
ExecStart=/usr/bin/docker run --name mssp-zeek --rm --net=host --cap-add=NET_ADMIN --cap-add=NET_RAW \\
  -v /opt/zeek-logs:/usr/local/zeek/spool/zeek \\
  zeek/zeek:7.0.7 zeek -i \${ZEEK_IF} local
ExecStop=/usr/bin/docker stop mssp-zeek
Environment=ZEEK_IF=\${ZEEK_IF}

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now mssp-zeek-docker.service
sleep 3
sudo systemctl is-active mssp-zeek-docker.service
sudo docker ps --filter name=mssp-zeek
REMOTE

echo "Zeek Docker service started on ${HOST} (interface ${ZEEK_IF})."
