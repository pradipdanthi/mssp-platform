#!/usr/bin/env bash
# Deploy Kevantic Appliance Management API onto VM 114 (channel / register / heartbeat).
# Prerequisites: VM created (create_proxmox_vm.sh). Publishes Postgres/Redis on VM100 loopback
# and reaches them from VM114 via SSH local forward (not LAN-exposed DB).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MGMT_IP="${KEVANTIC_MGMT_VM_IP:-192.168.0.224}"
MGMT_USER="${KEVANTIC_MGMT_CI_USER:-kevantic}"
SSH_KEY="${KEVANTIC_MGMT_SSH_KEY:-$ROOT/kevantic-appliance/.tools/build-ssh/kevantic_packer}"
CP_HOST="${MSSP_CONTROL_HOST:-192.168.0.201}"
CP_USER="${MSSP_CONTROL_USER:-secadmin}"
SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$SSH_KEY" "${MGMT_USER}@${MGMT_IP}")
SCP=(scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$SSH_KEY")

die() { echo "ERROR: $*" >&2; exit 1; }
[[ -f "$SSH_KEY" ]] || die "Missing SSH key $SSH_KEY"
[[ -f "$ROOT/.env" ]] || die "Missing $ROOT/.env (needed for DB/Redis credentials — not printed)"

echo "==> Ensure control-plane DB/Redis published on 127.0.0.1 (VM 100)"
cd "$ROOT"
docker compose up -d postgres redis
ss -lntp 2>/dev/null | grep -E '127\.0\.0\.1:5432|127\.0\.0\.1:6379' || true

echo "==> Install Docker on Appliance Management VM if needed"
"${SSH[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
if command -v docker >/dev/null 2>&1; then
  docker --version
  exit 0
fi
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$USER" || true
sudo systemctl enable --now docker
docker --version
REMOTE

echo "==> Ensure SSH tunnel key (114 → 100 loopback DB/Redis)"
TUNNEL_KEY="$HOME/.ssh/id_ed25519_appliance_mgmt_tunnel"
if [[ ! -f "$TUNNEL_KEY" ]]; then
  ssh-keygen -t ed25519 -N "" -f "$TUNNEL_KEY" -C "appliance-mgmt-db-tunnel" >/dev/null
fi
AUTH_LINE="$(cat "${TUNNEL_KEY}.pub")"
mkdir -p "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
chmod 600 "$HOME/.ssh/authorized_keys"
grep -qxF "$AUTH_LINE" "$HOME/.ssh/authorized_keys" || echo "$AUTH_LINE" >> "$HOME/.ssh/authorized_keys"
"${SCP[@]}" "$TUNNEL_KEY" "${MGMT_USER}@${MGMT_IP}:/home/${MGMT_USER}/.ssh/id_ed25519_cp_tunnel"
"${SSH[@]}" "chmod 600 /home/${MGMT_USER}/.ssh/id_ed25519_cp_tunnel"

echo "==> Install systemd SSH tunnel unit on VM 114"
UNIT_LOCAL=$(mktemp)
cat > "$UNIT_LOCAL" <<UNIT
[Unit]
Description=SSH tunnel to mssp-control Postgres/Redis (loopback)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${MGMT_USER}
ExecStart=/usr/bin/ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new -i /home/${MGMT_USER}/.ssh/id_ed25519_cp_tunnel -L 127.0.0.1:5432:127.0.0.1:5432 -L 127.0.0.1:6379:127.0.0.1:6379 ${CP_USER}@${CP_HOST}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
"${SCP[@]}" "$UNIT_LOCAL" "${MGMT_USER}@${MGMT_IP}:/tmp/kevantic-db-tunnel.service"
rm -f "$UNIT_LOCAL"
# Discrete remote steps (avoid nested-heredoc / stdin issues under ssh + sudo)
"${SSH[@]}" "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i \$HOME/.ssh/id_ed25519_cp_tunnel ${CP_USER}@${CP_HOST} 'echo TUNNEL_SSH_OK' >/dev/null"
"${SSH[@]}" 'pkill -f "ssh -N .*id_ed25519_cp_tunnel" 2>/dev/null || true; sleep 1'
"${SSH[@]}" 'sudo mv /tmp/kevantic-db-tunnel.service /etc/systemd/system/kevantic-db-tunnel.service'
"${SSH[@]}" 'sudo systemctl daemon-reload'
"${SSH[@]}" 'sudo systemctl enable --now kevantic-db-tunnel.service'
sleep 2
"${SSH[@]}" 'systemctl is-active kevantic-db-tunnel.service'
"${SSH[@]}" 'ss -lntp | grep -E "127\\.0\\.0\\.1:5432|127\\.0\\.0\\.1:6379" || true'

echo "==> Sync Appliance Management compose + backend source"
"${SSH[@]}" "sudo mkdir -p /opt/kevantic-appliance-mgmt && sudo chown ${MGMT_USER}:${MGMT_USER} /opt/kevantic-appliance-mgmt"
TAR_BUNDLE=$(mktemp /tmp/appliance-mgmt-src.XXXXXX.tgz)
tar -C "$ROOT" -czf "$TAR_BUNDLE" \
  --exclude='backend-api/**/__pycache__' \
  --exclude='backend-api/__pycache__' \
  --exclude='backend-api/.pytest_cache' \
  backend-api appliance-mgmt/docker-compose.yml
"${SCP[@]}" "$TAR_BUNDLE" "${MGMT_USER}@${MGMT_IP}:/tmp/appliance-mgmt-src.tgz"
rm -f "$TAR_BUNDLE"
"${SSH[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/kevantic-appliance-mgmt
rm -rf backend-api appliance-mgmt
tar -xzf /tmp/appliance-mgmt-src.tgz
mv -f appliance-mgmt/docker-compose.yml ./docker-compose.yml
rmdir appliance-mgmt 2>/dev/null || rm -rf appliance-mgmt
rm -f /tmp/appliance-mgmt-src.tgz
test -f backend-api/Dockerfile
test -f backend-api/app/main_appliance_mgmt.py
test -f docker-compose.yml
REMOTE

echo "==> Write .env on VM 114 (credentials copied, not printed)"
# Do not `source` control-plane .env — values like RESEND_FROM_EMAIL break bash.
REMOTE_ENV=$(mktemp)
chmod 600 "$REMOTE_ENV"
python3 - "$ROOT/.env" "$REMOTE_ENV" <<'PY'
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
env: dict[str, str] = {}
for line in src.read_text().splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1]
    env[k] = v

needed = [
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "JWT_SECRET",
]
missing = [k for k in needed if not env.get(k)]
if missing:
    raise SystemExit(f"missing keys in .env: {missing}")

out = {
    "APP_ENV": env.get("APP_ENV") or "production",
    "POSTGRES_HOST": "127.0.0.1",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": env["POSTGRES_DB"],
    "POSTGRES_USER": env["POSTGRES_USER"],
    "POSTGRES_PASSWORD": env["POSTGRES_PASSWORD"],
    "REDIS_HOST": "127.0.0.1",
    "REDIS_PORT": "6379",
    "REDIS_PASSWORD": env["REDIS_PASSWORD"],
    "JWT_SECRET": env["JWT_SECRET"],
    "TZ": env.get("TZ") or "Asia/Kolkata",
}
dst.write_text("".join(f"{k}={v}\n" for k, v in out.items()))
PY
"${SCP[@]}" "$REMOTE_ENV" "${MGMT_USER}@${MGMT_IP}:/opt/kevantic-appliance-mgmt/.env"
rm -f "$REMOTE_ENV"
"${SSH[@]}" 'chmod 600 /opt/kevantic-appliance-mgmt/.env'

echo "==> Build and start appliance-mgmt-api"
"${SSH[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/kevantic-appliance-mgmt
DOC=(docker)
if ! docker info >/dev/null 2>&1; then
  DOC=(sudo docker)
fi
"${DOC[@]}" compose -f docker-compose.yml build
"${DOC[@]}" compose -f docker-compose.yml up -d
sleep 4
"${DOC[@]}" compose -f docker-compose.yml ps
curl -fsS http://127.0.0.1:8000/health || true
echo
curl -fsS http://127.0.0.1:8000/ || true
echo
REMOTE

echo "==> Smoke from control plane → Appliance Management"
curl -fsS "http://${MGMT_IP}:8000/health"
echo
curl -fsS "http://${MGMT_IP}:8000/"
echo
echo APPLIANCE_MGMT_DEPLOY_OK
