#!/usr/bin/env bash
# Bake Sovereign Edge full-stack modules into golden VM 199 (compose + portal; docker optional).
# Stages files for sovereign_edge tenants — does not auto-start Docker stacks unless
# MSSP_GOLDEN_SOVEREIGN_FULL_STACK_DOCKER=1 and VM has sufficient RAM.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CTRL="$(cd "$ROOT/.." && pwd)"
PVE_HOST="${KEVANTIC_PVE_HOST:-192.168.0.191}"
PVE_KEY="${KEVANTIC_PVE_SSH_KEY:-$HOME/.ssh/id_ed25519_proxmox}"
VMID="${MSSP_GOLDEN_VMID:-199}"
HOST="${MSSP_GOLDEN_VM_IP:-192.168.0.225}"
USER_NAME="${MSSP_GOLDEN_SSH_USER:-packer}"
SSH_KEY="${MSSP_BUILD_SSH_KEY:-$ROOT/.tools/build-ssh/kevantic_packer}"
START_DOCKER="${MSSP_GOLDEN_SOVEREIGN_FULL_STACK_DOCKER:-0}"

PVE_SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$PVE_KEY" "root@${PVE_HOST}")
SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "${USER_NAME}@${HOST}")
SCP=(scp -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new)

log() { printf '[bake-golden-199-fullstack] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

[[ -f "$SSH_KEY" ]] || die "missing SSH key $SSH_KEY"

status="$("${PVE_SSH[@]}" "qm status ${VMID}" | awk '{print $2}')"
if [[ "$status" != "running" ]]; then
  log "Starting VM ${VMID}"
  "${PVE_SSH[@]}" "qm start ${VMID}"
fi

ready=0
for _ in $(seq 1 60); do
  if "${SSH[@]}" 'echo SSH_OK' >/dev/null 2>&1; then ready=1; break; fi
  sleep 4
done
[[ "$ready" -eq 1 ]] || die "SSH timeout to golden ${HOST}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -r "$ROOT/appliance/sovereign" "$TMP/sovereign"
cp "$ROOT/scripts/sovereign_full_stack.sh" "$TMP/sovereign_full_stack.sh"
cp "$ROOT/scripts/sovereign_full_stack_stub.sh" "$TMP/sovereign_full_stack_stub.sh"
cp "$ROOT/scripts/enable_sovereign_full_stack_on_appliance.sh" "$TMP/enable_sovereign_full_stack_on_appliance.sh"

"${SCP[@]}" -r "$TMP/sovereign" "$TMP/sovereign_full_stack.sh" "$TMP/sovereign_full_stack_stub.sh" \
  "$TMP/enable_sovereign_full_stack_on_appliance.sh" "${USER_NAME}@${HOST}:/tmp/"

"${SSH[@]}" "bash -s" <<REMOTE
set -euo pipefail
sudo install -d -m 0755 /opt/kevantic/appliance-src/appliance/sovereign/compose /opt/niktiar/appliance-src/appliance/sovereign/compose
for f in full_stack.py unified_portal.py portal_auth.py rbac.py profile.py cluster.py node_agent.py renewal_reminder.py; do
  [[ -f /tmp/sovereign/\$f ]] && sudo install -m 0644 "/tmp/sovereign/\$f" "/opt/kevantic/appliance-src/appliance/sovereign/\$f"
  [[ -f /tmp/sovereign/\$f ]] && sudo install -m 0644 "/tmp/sovereign/\$f" "/opt/niktiar/appliance-src/appliance/sovereign/\$f"
done
sudo install -m 0644 /tmp/sovereign/compose/*.yml /opt/kevantic/appliance-src/appliance/sovereign/compose/
sudo install -m 0644 /tmp/sovereign/compose/*.yml /opt/niktiar/appliance-src/appliance/sovereign/compose/
sudo install -m 0755 /tmp/sovereign_full_stack.sh /usr/local/sbin/sovereign-full-stack
sudo install -m 0755 /tmp/sovereign_full_stack_stub.sh /usr/local/sbin/sovereign-full-stack-stub
sudo install -d -m 0750 /opt/kevantic/sovereign-full-stack /opt/niktiar/sovereign-full-stack
sudo install -m 0640 /tmp/sovereign/compose/thehive-docker-compose.yml /opt/kevantic/sovereign-full-stack/
sudo install -m 0640 /tmp/sovereign/compose/shuffle-docker-compose.yml /opt/kevantic/sovereign-full-stack/
sudo install -m 0640 /tmp/sovereign/compose/thehive-docker-compose.yml /opt/niktiar/sovereign-full-stack/
sudo install -m 0640 /tmp/sovereign/compose/shuffle-docker-compose.yml /opt/niktiar/sovereign-full-stack/
sudo install -d -m 0755 /var/lib/kevantic/sovereign-full-stack /var/lib/niktiar/sovereign-full-stack /run/sovereign-full-stack
sudo env SOVEREIGN_FULL_STACK_MODE=preflight /usr/local/sbin/sovereign-full-stack enable
REMOTE

if [[ "$START_DOCKER" == "1" ]]; then
  log "Docker start requested — attempting docker mode on golden VM"
  "${SSH[@]}" 'sudo sysctl -w vm.max_map_count=262144; sudo sovereign-full-stack docker-start || true'
fi

SNAP_NAME="${MSSP_GOLDEN_SNAPSHOT_NAME:-kb114-sovereign-fullstack-$(date -u +%Y%m%d%H%M)}"
log "Shutting down VM ${VMID} and taking snapshot ${SNAP_NAME}"
"${PVE_SSH[@]}" "qm shutdown ${VMID} --timeout 120 || qm stop ${VMID} --timeout 30"
sleep 5
"${PVE_SSH[@]}" "qm snapshot ${VMID} ${SNAP_NAME} --description 'KB-114 sovereign full stack bake'"
log "DONE: golden VM ${VMID} snapshot ${SNAP_NAME}"
