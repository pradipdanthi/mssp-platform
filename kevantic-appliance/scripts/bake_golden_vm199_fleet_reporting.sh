#!/usr/bin/env bash
# Bake fleet-reporting (heartbeat inventory + CPU/mem/disk + image-release) into golden VM 199.
# Does NOT seed lab entitlements — clones stay idle until licensed.
# After bake, VM 199 is shut down so it remains a clean clone source.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CTRL="$(cd "$ROOT/.." && pwd)"
PVE_HOST="${KEVANTIC_PVE_HOST:-192.168.0.191}"
PVE_KEY="${KEVANTIC_PVE_SSH_KEY:-$HOME/.ssh/id_ed25519_proxmox}"
VMID="${MSSP_GOLDEN_VMID:-199}"
HOST="${MSSP_GOLDEN_VM_IP:-192.168.0.225}"
USER_NAME="${MSSP_GOLDEN_SSH_USER:-packer}"
SSH_KEY="${MSSP_BUILD_SSH_KEY:-$ROOT/.tools/build-ssh/kevantic_packer}"
KEEP_RUNNING="${MSSP_GOLDEN_KEEP_RUNNING:-0}"
SNAP_NAME="${MSSP_GOLDEN_SNAPSHOT_NAME:-}"

PVE_SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$PVE_KEY" "root@${PVE_HOST}")
SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "${USER_NAME}@${HOST}")
SCP=(scp -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new)

log() { printf '[bake-golden-199] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

[[ -f "$PVE_KEY" ]] || die "missing Proxmox SSH key: $PVE_KEY"
[[ -f "$SSH_KEY" ]] || die "missing appliance SSH key: $SSH_KEY"
[[ -f "$ROOT/cli/kevantic-cli/kevantic_cli/register_ops.py" ]] || die "CLI source missing"
[[ -f "$ROOT/configs/systemd/kevantic-heartbeat.service" ]] || die "heartbeat unit missing"
[[ -f "$ROOT/configs/systemd/kevantic-license-enforce.service" ]] || die "license enforce unit missing"
[[ -f "$ROOT/cli/kevantic-cli/kevantic_cli/license_ops.py" ]] || die "license_ops.py missing"
PUBKEY="$ROOT/licensing/keys/licensing-ed25519-v1.pub"
[[ -f "$PUBKEY" ]] || die "missing $PUBKEY — run kevantic-appliance/licensing/generate_dev_keypair.sh"

GIT_COMMIT="$(git -C "$CTRL" rev-parse --short HEAD 2>/dev/null || echo unknown)"

log "Starting Proxmox VM ${VMID} if stopped"
status="$("${PVE_SSH[@]}" "qm status ${VMID}" | awk '{print $2}')"
if [[ "$status" != "running" ]]; then
  "${PVE_SSH[@]}" "qm start ${VMID}"
fi

log "Waiting for SSH as ${USER_NAME}@${HOST}"
ready=0
for i in $(seq 1 90); do
  if "${SSH[@]}" 'echo SSH_OK' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 4
done
[[ "$ready" -eq 1 ]] || die "SSH timeout to golden ${HOST} — check Proxmox console VM ${VMID}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp "$ROOT/cli/kevantic-cli/kevantic_cli/register_ops.py" "$TMP/register_ops.py"
cp "$ROOT/cli/kevantic-cli/kevantic_cli/state.py" "$TMP/state.py"
cp "$ROOT/cli/kevantic-cli/kevantic_cli/license_ops.py" "$TMP/license_ops.py"
cp "$ROOT/configs/systemd/kevantic-heartbeat.service" "$TMP/kevantic-heartbeat.service"
cp "$ROOT/configs/systemd/kevantic-heartbeat.timer" "$TMP/kevantic-heartbeat.timer"
cp "$ROOT/configs/systemd/junexis-heartbeat.service" "$TMP/junexis-heartbeat.service"
cp "$ROOT/configs/systemd/junexis-heartbeat.timer" "$TMP/junexis-heartbeat.timer"
cp "$ROOT/configs/systemd/kevantic-license-enforce.service" "$TMP/kevantic-license-enforce.service"
cp "$ROOT/configs/systemd/kevantic-license-enforce.timer" "$TMP/kevantic-license-enforce.timer"
cp "$PUBKEY" "$TMP/licensing-ed25519-v1.pub"
cp "$ROOT/configs/image-release.json" "$TMP/image-release.json"
AR_SRC="$CTRL/deploy/wazuh-active-response"
[[ -x "$AR_SRC/mssp-isolate-host" ]] || die "missing Linux AR scripts in deploy/wazuh-active-response"
cp "$AR_SRC/mssp-isolate-host" "$AR_SRC/mssp-kill-process" "$AR_SRC/mssp-block-hash" "$TMP/"
WIN_AR="$AR_SRC/windows"
[[ -f "$WIN_AR/mssp-isolate-host.ps1" ]] || die "missing Windows isolate script"
[[ -f "$WIN_AR/Watch-MsspQuarantine.ps1" ]] || die "missing Windows isolate watchdog"
mkdir -p "$TMP/win-ar"
WIN_AR_FILES=(
  mssp-isolate-host.ps1 mssp-isolate-host.cmd
  mssp-kill-process.ps1 mssp-kill-process.cmd
  mssp-block-hash.ps1 mssp-block-hash.cmd
  Sync-MsspEdrAr.ps1 Watch-MsspQuarantine.ps1
)
for f in "${WIN_AR_FILES[@]}"; do
  [[ -f "$WIN_AR/$f" ]] || die "missing Windows AR file: $f"
  cp "$WIN_AR/$f" "$TMP/win-ar/"
done
LINUX_EDR_RULES="$CTRL/deploy/wazuh-manager/mssp_linux_exec_rules.xml"
LINUX_EDR_SH="$CTRL/backend-api/app/endpoint_configs/linux-edr-telemetry/install-mssp-linux-telemetry.sh"
LINUX_EDR_AUDIT="$CTRL/backend-api/app/endpoint_configs/linux-edr-telemetry/mssp-exec.rules"
[[ -f "$LINUX_EDR_RULES" ]] || die "missing $LINUX_EDR_RULES"
[[ -f "$LINUX_EDR_SH" ]] || die "missing $LINUX_EDR_SH"
cp "$LINUX_EDR_RULES" "$TMP/mssp_linux_exec_rules.xml"
cp "$LINUX_EDR_SH" "$TMP/install-mssp-linux-telemetry.sh"
cp "$LINUX_EDR_AUDIT" "$TMP/mssp-exec.rules"
python3 - "$TMP/image-release.json" "$GIT_COMMIT" <<'PY'
import json, sys
path, commit = sys.argv[1], sys.argv[2]
data = json.loads(open(path, encoding="utf-8").read())
data["git_commit"] = commit
open(path, "w", encoding="utf-8").write(json.dumps(data, indent=2) + "\n")
PY

log "Installing CLI, heartbeat units, and image-release on ${HOST} (git_commit=${GIT_COMMIT})"
"${SCP[@]}" \
  "$TMP/register_ops.py" \
  "$TMP/state.py" \
  "$TMP/license_ops.py" \
  "$TMP/kevantic-heartbeat.service" \
  "$TMP/kevantic-heartbeat.timer" \
  "$TMP/junexis-heartbeat.service" \
  "$TMP/junexis-heartbeat.timer" \
  "$TMP/kevantic-license-enforce.service" \
  "$TMP/kevantic-license-enforce.timer" \
  "$TMP/licensing-ed25519-v1.pub" \
  "$TMP/image-release.json" \
  "$TMP/mssp-isolate-host" \
  "$TMP/mssp-kill-process" \
  "$TMP/mssp-block-hash" \
  "$TMP/win-ar/mssp-isolate-host.ps1" \
  "$TMP/win-ar/mssp-isolate-host.cmd" \
  "$TMP/win-ar/mssp-kill-process.ps1" \
  "$TMP/win-ar/mssp-kill-process.cmd" \
  "$TMP/win-ar/mssp-block-hash.ps1" \
  "$TMP/win-ar/mssp-block-hash.cmd" \
  "$TMP/win-ar/Sync-MsspEdrAr.ps1" \
  "$TMP/win-ar/Watch-MsspQuarantine.ps1" \
  "$TMP/mssp_linux_exec_rules.xml" \
  "$TMP/install-mssp-linux-telemetry.sh" \
  "$TMP/mssp-exec.rules" \
  "${USER_NAME}@${HOST}:/tmp/"

"${SSH[@]}" "bash -s" <<REMOTE
set -euo pipefail
CLI="/opt/kevantic/cli/kevantic_cli"
if [[ ! -d "\$CLI" ]]; then
  CLI="/opt/junexis/cli/junexis_cli"
fi
[[ -d "\$CLI" ]] || { echo "CLI directory missing" >&2; exit 2; }

sudo install -m 0644 /tmp/register_ops.py "\$CLI/register_ops.py"
sudo install -m 0644 /tmp/state.py "\$CLI/state.py"
sudo install -m 0644 /tmp/license_ops.py "\$CLI/license_ops.py"
sudo install -d -m 0755 /etc/kevantic /etc/junexis /etc/kevantic/trust/keys /etc/junexis/trust/keys
sudo install -m 0644 /tmp/licensing-ed25519-v1.pub /etc/kevantic/trust/keys/licensing-ed25519-v1.pub
sudo install -m 0644 /tmp/licensing-ed25519-v1.pub /etc/junexis/trust/keys/licensing-ed25519-v1.pub
sudo install -m 0644 /tmp/image-release.json /etc/kevantic/image-release.json
sudo install -m 0644 /tmp/image-release.json /etc/junexis/image-release.json
sudo install -m 0644 /tmp/kevantic-heartbeat.service /etc/systemd/system/kevantic-heartbeat.service
sudo install -m 0644 /tmp/kevantic-heartbeat.timer /etc/systemd/system/kevantic-heartbeat.timer
sudo install -m 0644 /tmp/junexis-heartbeat.service /etc/systemd/system/junexis-heartbeat.service
sudo install -m 0644 /tmp/junexis-heartbeat.timer /etc/systemd/system/junexis-heartbeat.timer
sudo install -m 0644 /tmp/kevantic-license-enforce.service /etc/systemd/system/kevantic-license-enforce.service
sudo install -m 0644 /tmp/kevantic-license-enforce.timer /etc/systemd/system/kevantic-license-enforce.timer
for f in mssp-isolate-host mssp-kill-process mssp-block-hash; do
  sudo install -o root -g wazuh -m 0750 "/tmp/\$f" "/var/ossec/active-response/bin/\$f"
done
sudo install -d -m 0755 /var/lib/junexis/edr-ar/windows /var/lib/kevantic/edr-ar/windows
sudo install -d -m 0755 /var/lib/junexis/edr-ar/linux /var/lib/kevantic/edr-ar/linux
for f in mssp-isolate-host.ps1 mssp-isolate-host.cmd mssp-kill-process.ps1 mssp-kill-process.cmd mssp-block-hash.ps1 mssp-block-hash.cmd Sync-MsspEdrAr.ps1 Watch-MsspQuarantine.ps1; do
  if [[ -f /tmp/\$f ]]; then
    sudo install -o wazuh -g wazuh -m 0640 "/tmp/\$f" "/var/lib/junexis/edr-ar/windows/\$f"
    sudo install -o wazuh -g wazuh -m 0640 "/tmp/\$f" "/var/lib/kevantic/edr-ar/windows/\$f"
  fi
done
for f in mssp_linux_exec_rules.xml install-mssp-linux-telemetry.sh mssp-exec.rules; do
  if [[ -f /tmp/\$f ]]; then
    sudo install -o wazuh -g wazuh -m 0640 "/tmp/\$f" "/var/lib/junexis/edr-ar/linux/\$f"
    sudo install -o wazuh -g wazuh -m 0640 "/tmp/\$f" "/var/lib/kevantic/edr-ar/linux/\$f"
  fi
done
# Register isolate/kill/block command names on the local Manager (Windows + Linux).
if [[ -d /opt/junexis/cli/junexis_cli ]]; then
  sudo env PYTHONPATH=/opt/junexis/cli:/opt/junexis python3 -c 'from junexis_cli.register_ops import _ensure_local_edr_ar_commands; _ensure_local_edr_ar_commands()'
else
  sudo env PYTHONPATH=/opt/kevantic/cli:/opt/kevantic python3 -c 'from kevantic_cli.register_ops import _ensure_local_edr_ar_commands; _ensure_local_edr_ar_commands()'
fi
sudo grep -q '<name>mssp-isolate-host.cmd</name>' /var/ossec/etc/ossec.conf

if [[ -x /usr/bin/kevantic-list-local-agents ]] && [[ ! -e /usr/bin/junexis-list-local-agents ]]; then
  sudo ln -sf /usr/bin/kevantic-list-local-agents /usr/bin/junexis-list-local-agents
fi

sudo systemctl daemon-reload
sudo systemctl enable kevantic-heartbeat.timer >/dev/null
sudo systemctl restart kevantic-heartbeat.timer || true
sudo systemctl enable kevantic-license-enforce.timer >/dev/null
sudo systemctl restart kevantic-license-enforce.timer || true

echo "== verify =="
grep -F 'python3 -m kevantic_cli heartbeat' /etc/systemd/system/kevantic-heartbeat.service
grep -F 'python3 -m kevantic_cli license enforce' /etc/systemd/system/kevantic-license-enforce.service
grep -F 'OnUnitActiveSec=1h' /etc/systemd/system/kevantic-license-enforce.timer
grep -F 'OnBootSec=3min' /etc/systemd/system/kevantic-license-enforce.timer
sudo systemctl is-enabled kevantic-license-enforce.timer | grep -qx enabled
grep -E '_collect_resource_metrics|_read_enabled_services|_read_image_metadata|apply_entitlements|license_jws|_authenticate_local_wazuh|_ensure_local_edr_ar_commands|_publish_linux_midlayer_shared' "\$CLI/register_ops.py" >/dev/null
sudo test -f /etc/kevantic/trust/keys/licensing-ed25519-v1.pub
sudo test -f /var/lib/kevantic/edr-ar/linux/mssp_linux_exec_rules.xml
python3 -c 'import json; d=json.load(open("/etc/kevantic/image-release.json")); assert d.get("git_commit") and d.get("config_version")'
# Do not seed entitlements — golden clones stay idle until a real license is applied.
if [[ -f /var/lib/kevantic/entitlements.json ]]; then
  python3 - <<'PY'
import json
from pathlib import Path
p = Path("/var/lib/kevantic/entitlements.json")
data = json.loads(p.read_text())
svcs = data.get("service_ids") or []
note = str(data.get("note") or "")
if "seeded" in note.lower() or "lab core entitlement" in note.lower():
    raise SystemExit("golden entitlements were lab-seeded — abort")
print("entitlements_service_ids", svcs)
PY
fi
echo GOLDEN_FLEET_BAKE_OK
REMOTE

if [[ "$KEEP_RUNNING" == "1" ]]; then
  log "Leaving VM ${VMID} running (MSSP_GOLDEN_KEEP_RUNNING=1)"
else
  log "Shutting down golden VM ${VMID} (clone source stays stopped)"
  "${PVE_SSH[@]}" "qm shutdown ${VMID} --timeout 90 || qm stop ${VMID} --timeout 30"
  sleep 3
  "${PVE_SSH[@]}" "qm status ${VMID}"
fi

if [[ -n "$SNAP_NAME" ]]; then
  log "Taking Proxmox snapshot ${VMID} → ${SNAP_NAME}"
  "${PVE_SSH[@]}" "qm snapshot ${VMID} ${SNAP_NAME} --description 'Golden bake git=${GIT_COMMIT} license pubkey + enforce timer'"
  "${PVE_SSH[@]}" "qm listsnapshot ${VMID}"
fi

log "OK — golden VM ${VMID} now includes fleet reporting (git_commit=${GIT_COMMIT})"
echo GOLDEN_FLEET_BAKE_OK
