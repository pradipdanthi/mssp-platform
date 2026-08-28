#!/usr/bin/env bash
# Migrate a live appliance from legacy Junexis paths/units to NikTiar branding.
# Safe to re-run. Does not rename the Linux OS user (junexis@) — SSH stays working.
#
# Usage: ./kevantic-appliance/scripts/upgrade_junexis_to_niktiar_brand.sh 192.168.0.226 [ssh-user]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CTRL="$(cd "$ROOT/.." && pwd)"
HOST="${1:-}"
USER_NAME="${2:-junexis}"
SSH_KEY="${MSSP_BUILD_SSH_KEY:-$ROOT/.tools/build-ssh/kevantic_packer}"

[[ -n "$HOST" ]] || { echo "Usage: $0 <appliance-ip> [ssh-user]" >&2; exit 1; }
[[ -f "$SSH_KEY" ]] || { echo "Missing SSH key: $SSH_KEY" >&2; exit 1; }

SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${USER_NAME}@${HOST}")
SCP=(scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cp "$ROOT/configs/systemd/niktiar-heartbeat.service" "$TMP/"
cp "$ROOT/configs/systemd/niktiar-heartbeat.timer" "$TMP/"
cp "$ROOT/configs/systemd/niktiar-critical-alert-forwarder.service" "$TMP/"
cp "$CTRL/kevantic-appliance/cli/kevantic-cli/kevantic_cli/register_ops.py" "$TMP/"
cp "$CTRL/kevantic-appliance/cli/kevantic-cli/kevantic_cli/state.py" "$TMP/"
cp "$CTRL/kevantic-appliance/cli/kevantic-cli/kevantic_cli/license_ops.py" "$TMP/"
cp "$CTRL/kevantic-appliance/appliance/common/paths.py" "$TMP/"
cp "$CTRL/kevantic-appliance/appliance/telemetry/critical_alert_watcher.py" "$TMP/"
cp "$CTRL/kevantic-appliance/appliance/telemetry/forwarder.py" "$TMP/"

echo "==> Uploading NikTiar units + CLI to ${USER_NAME}@${HOST}"
"${SCP[@]}" "$TMP"/* "${USER_NAME}@${HOST}:/tmp/"

"${SSH[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
sudo mkdir -p /opt/niktiar/cli /etc/niktiar/trust/keys /var/lib/niktiar /var/log/niktiar /run/niktiar

# Legacy path aliases (do not move data — symlink only)
for pair in \
  "/opt/niktiar /opt/junexis" \
  "/etc/niktiar /etc/junexis" \
  "/var/lib/niktiar /var/lib/junexis" \
  "/var/log/niktiar /var/log/junexis" \
  "/run/niktiar /run/junexis"; do
  read -r new old <<<"$pair"
  if [[ -d "$old" && ! -e "$new" ]]; then
    sudo ln -s "$old" "$new"
    echo "symlink $new -> $old"
  fi
done
if [[ -d /opt/junexis/appliance-src && ! -e /opt/niktiar/appliance-src ]]; then
  sudo ln -sf /opt/junexis/appliance-src /opt/niktiar/appliance-src
  echo "symlink /opt/niktiar/appliance-src -> /opt/junexis/appliance-src"
fi

# CLI package: niktiar_cli (copy from junexis_cli or kevantic_cli)
if [[ -d /opt/junexis/cli/junexis_cli && ! -d /opt/niktiar/cli/niktiar_cli ]]; then
  sudo mkdir -p /opt/niktiar/cli
  sudo cp -a /opt/junexis/cli/junexis_cli /opt/niktiar/cli/niktiar_cli
  echo "copied junexis_cli -> niktiar_cli"
elif [[ -d /opt/kevantic/cli/kevantic_cli && ! -d /opt/niktiar/cli/niktiar_cli ]]; then
  sudo mkdir -p /opt/niktiar/cli
  sudo cp -a /opt/kevantic/cli/kevantic_cli /opt/niktiar/cli/niktiar_cli
fi

if [[ -d /opt/niktiar/cli/niktiar_cli ]]; then
  sudo find /opt/niktiar/cli/niktiar_cli -type f -name '*.py' -exec sed -i 's/junexis_cli/niktiar_cli/g' {} +
  sudo install -m 0644 /tmp/register_ops.py /opt/niktiar/cli/niktiar_cli/register_ops.py
  sudo install -m 0644 /tmp/state.py /opt/niktiar/cli/niktiar_cli/state.py
  sudo install -m 0644 /tmp/license_ops.py /opt/niktiar/cli/niktiar_cli/license_ops.py
fi

if [[ -f /etc/junexis/appliance.env && ! -f /etc/niktiar/appliance.env ]]; then
  sudo ln -sf /etc/junexis/appliance.env /etc/niktiar/appliance.env
fi
if [[ -f /etc/kevantic/trust/keys/licensing-ed25519-v1.pub ]]; then
  sudo install -m 0644 /etc/kevantic/trust/keys/licensing-ed25519-v1.pub /etc/niktiar/trust/keys/licensing-ed25519-v1.pub 2>/dev/null || true
fi

if [[ -d /opt/niktiar/appliance-src/appliance ]] || [[ -d /opt/junexis/appliance-src/appliance ]]; then
  dst=/opt/niktiar/appliance-src/appliance
  [[ -d "$dst" ]] || dst=/opt/junexis/appliance-src/appliance
  sudo install -m 0644 /tmp/paths.py "$dst/common/paths.py"
  sudo install -m 0644 /tmp/critical_alert_watcher.py "$dst/telemetry/critical_alert_watcher.py"
  sudo install -m 0644 /tmp/forwarder.py "$dst/telemetry/forwarder.py"
fi

# Legacy boxes: units must see junexis appliance-src + cli on PYTHONPATH
sudo tee /etc/systemd/system/niktiar-heartbeat.service >/dev/null <<'HB'
[Unit]
Description=NikTiar appliance heartbeat (health + agent inventory + job pull)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=-/etc/niktiar/appliance.env
EnvironmentFile=-/etc/junexis/appliance.env
Environment=PYTHONPATH=/opt/niktiar/cli:/opt/junexis/cli:/opt/niktiar:/opt/junexis
ExecStart=/usr/bin/python3 -m niktiar_cli heartbeat --json
Nice=10

[Install]
WantedBy=multi-user.target
HB

sudo tee /etc/systemd/system/niktiar-critical-alert-forwarder.service >/dev/null <<'FWD'
[Unit]
Description=NikTiar critical-alert forwarder (local Manager → cloud SOC metadata)
After=network-online.target wazuh-manager.service
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=-/etc/niktiar/appliance.env
EnvironmentFile=-/etc/junexis/appliance.env
EnvironmentFile=-/etc/kevantic/appliance.env
Environment=PYTHONPATH=/opt/niktiar/appliance-src:/opt/junexis/appliance-src:/opt/kevantic/appliance-src:/opt/niktiar:/opt/junexis:/opt/kevantic
Environment=NIKTIAR_STATE_DIR=/var/lib/niktiar
Environment=NIKTIAR_LOG_DIR=/var/log/niktiar
Environment=JUNEXIS_STATE_DIR=/var/lib/junexis
Environment=JUNEXIS_LOG_DIR=/var/log/junexis
Environment=NIKTIAR_FORWARD_MIN_LEVEL=10
Environment=KEVANTIC_FORWARD_MIN_LEVEL=10
Environment=NIKTIAR_WAZUH_ALERTS_PATH=/var/ossec/logs/alerts/alerts.json
Environment=ENABLE_LOCAL_AI_FILTER=false
Environment=LOCAL_AI_FAIL_OPEN=true
ExecStartPre=/bin/mkdir -p /var/lib/niktiar /var/log/niktiar /run/niktiar /var/lib/junexis /var/log/junexis
ExecStart=/usr/bin/python3 -m appliance.telemetry.critical_alert_watcher
Restart=always
RestartSec=5
Nice=5

[Install]
WantedBy=multi-user.target
FWD

sudo install -m 0644 /tmp/niktiar-heartbeat.timer /etc/systemd/system/niktiar-heartbeat.timer

sudo systemctl daemon-reload
sudo systemctl enable niktiar-heartbeat.timer niktiar-critical-alert-forwarder.service
sudo systemctl disable --now junexis-heartbeat.timer junexis-critical-alert-forwarder.service 2>/dev/null || true
sudo systemctl start niktiar-heartbeat.timer || true
sudo systemctl restart niktiar-critical-alert-forwarder.service || true
sudo systemctl start niktiar-heartbeat.service || true

echo "NikTiar units:"
systemctl is-active niktiar-heartbeat.timer niktiar-critical-alert-forwarder.service || true
REMOTE

echo "==> OK — NikTiar brand migration applied on ${HOST}"
