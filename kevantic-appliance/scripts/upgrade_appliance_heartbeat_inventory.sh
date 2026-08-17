#!/usr/bin/env bash
# One-time field fix: heartbeat timer must call python -m …, not the bash CLI wrapper.
# Without this, agent_inventory is empty and new endpoint agents never reach the dashboard.
# Golden VM 199: use scripts/bake_golden_vm199_fleet_reporting.sh (recipe also ships python -m).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${1:-}"
USER_NAME="${2:-junexis}"

usage() {
  echo "Usage: $0 <appliance-ip> [ssh-user]" >&2
  echo "Example: $0 192.168.0.226 junexis" >&2
  exit 1
}

[[ -n "$HOST" ]] || usage

SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${USER_NAME}@${HOST}")

echo "==> Patching heartbeat units on ${HOST}"
"${SSH[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
patch_unit() {
  local unit="$1"
  local module="$2"
  local py_path="$3"
  local env_file="$4"
  [[ -f "/etc/systemd/system/${unit}" ]] || return 0
  sudo tee "/etc/systemd/system/${unit}" >/dev/null <<EOF
[Unit]
Description=Appliance heartbeat (health + agent inventory + job pull)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=-${env_file}
Environment=PYTHONPATH=${py_path}
ExecStart=/usr/bin/python3 -m ${module} heartbeat --json
Nice=10

[Install]
WantedBy=multi-user.target
EOF
  echo "patched ${unit}"
}

patch_unit kevantic-heartbeat.service kevantic_cli /opt/kevantic/cli:/opt/kevantic /etc/kevantic/appliance.env
patch_unit junexis-heartbeat.service junexis_cli /opt/junexis/cli:/opt/junexis /etc/junexis/appliance.env

if [[ -f /usr/bin/kevantic-list-local-agents ]] && [[ ! -f /usr/bin/junexis-list-local-agents ]]; then
  sudo ln -sf /usr/bin/kevantic-list-local-agents /usr/bin/junexis-list-local-agents
fi

sudo systemctl daemon-reload
for t in kevantic-heartbeat.timer junexis-heartbeat.timer; do
  if systemctl list-unit-files "$t" --no-legend 2>/dev/null | grep -q .; then
    sudo systemctl restart "$t"
    sudo systemctl start "${t%.timer}.service" || true
  fi
done
REMOTE

echo "==> OK — heartbeat inventory fix applied on ${HOST}"
