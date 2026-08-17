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

PVE_SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$PVE_KEY" "root@${PVE_HOST}")
SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "${USER_NAME}@${HOST}")
SCP=(scp -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new)

log() { printf '[bake-golden-199] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

[[ -f "$PVE_KEY" ]] || die "missing Proxmox SSH key: $PVE_KEY"
[[ -f "$SSH_KEY" ]] || die "missing appliance SSH key: $SSH_KEY"
[[ -f "$ROOT/cli/kevantic-cli/kevantic_cli/register_ops.py" ]] || die "CLI source missing"
[[ -f "$ROOT/configs/systemd/kevantic-heartbeat.service" ]] || die "heartbeat unit missing"

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
cp "$ROOT/configs/systemd/kevantic-heartbeat.service" "$TMP/kevantic-heartbeat.service"
cp "$ROOT/configs/systemd/kevantic-heartbeat.timer" "$TMP/kevantic-heartbeat.timer"
cp "$ROOT/configs/systemd/junexis-heartbeat.service" "$TMP/junexis-heartbeat.service"
cp "$ROOT/configs/systemd/junexis-heartbeat.timer" "$TMP/junexis-heartbeat.timer"
cp "$ROOT/configs/image-release.json" "$TMP/image-release.json"
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
  "$TMP/kevantic-heartbeat.service" \
  "$TMP/kevantic-heartbeat.timer" \
  "$TMP/junexis-heartbeat.service" \
  "$TMP/junexis-heartbeat.timer" \
  "$TMP/image-release.json" \
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
sudo install -d -m 0755 /etc/kevantic /etc/junexis
sudo install -m 0644 /tmp/image-release.json /etc/kevantic/image-release.json
sudo install -m 0644 /tmp/image-release.json /etc/junexis/image-release.json
sudo install -m 0644 /tmp/kevantic-heartbeat.service /etc/systemd/system/kevantic-heartbeat.service
sudo install -m 0644 /tmp/kevantic-heartbeat.timer /etc/systemd/system/kevantic-heartbeat.timer
sudo install -m 0644 /tmp/junexis-heartbeat.service /etc/systemd/system/junexis-heartbeat.service
sudo install -m 0644 /tmp/junexis-heartbeat.timer /etc/systemd/system/junexis-heartbeat.timer

if [[ -x /usr/bin/kevantic-list-local-agents ]] && [[ ! -e /usr/bin/junexis-list-local-agents ]]; then
  sudo ln -sf /usr/bin/kevantic-list-local-agents /usr/bin/junexis-list-local-agents
fi

sudo systemctl daemon-reload
sudo systemctl enable kevantic-heartbeat.timer >/dev/null
sudo systemctl restart kevantic-heartbeat.timer || true

echo "== verify =="
grep -F 'python3 -m kevantic_cli heartbeat' /etc/systemd/system/kevantic-heartbeat.service
grep -E '_collect_resource_metrics|_read_enabled_services|_read_image_metadata|apply_entitlements' "\$CLI/register_ops.py" >/dev/null
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

log "OK — golden VM ${VMID} now includes fleet reporting (git_commit=${GIT_COMMIT})"
echo GOLDEN_FLEET_BAKE_OK
