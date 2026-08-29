#!/usr/bin/env bash
# KB-115 Step 7: Ephemeral 2-VM sovereign HA — clone, provision, validate.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PVE_HOST="${KEVANTIC_PVE_HOST:-192.168.0.191}"
PVE_KEY="${KEVANTIC_PVE_SSH_KEY:-$HOME/.ssh/id_ed25519_proxmox}"
SOURCE_VMID="${SOVEREIGN_HA_SOURCE_VMID:-210}"
NODE_A_VMID="${SOVEREIGN_HA_NODE_A_VMID:-221}"
NODE_B_VMID="${SOVEREIGN_HA_NODE_B_VMID:-222}"
NODE_A_IP="${SOVEREIGN_HA_NODE_A_IP:-192.168.0.231}"
NODE_B_IP="${SOVEREIGN_HA_NODE_B_IP:-192.168.0.232}"
APPLIANCE_USER="${APPLIANCE_SSH_USER:-junexis}"
APPLIANCE_KEY="${APPLIANCE_SSH_KEY:-$ROOT/kevantic-appliance/.tools/build-ssh/kevantic_packer}"
CLUSTER_ID="${SOVEREIGN_CLUSTER_ID:-$(uuidgen 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())')}"
JOIN_TOKEN="${SOVEREIGN_JOIN_TOKEN:-kb115-$(date +%s)}"
SKIP_CLONE="${SOVEREIGN_HA_SKIP_CLONE:-0}"
HA_MODE="${SOVEREIGN_HA_MODE:-auto}"

PVE=(ssh -o BatchMode=yes -i "$PVE_KEY" "root@${PVE_HOST}")
BETA_HOST="${APPLIANCE_SSH_HOST:-192.168.0.226}"
SSH_BETA=(ssh -i "$APPLIANCE_KEY" -o BatchMode=yes -o StrictHostKeyChecking=no "${APPLIANCE_USER}@${BETA_HOST}")
SSH_A=(ssh -i "$APPLIANCE_KEY" -o BatchMode=yes -o StrictHostKeyChecking=no "${APPLIANCE_USER}@${NODE_A_IP}")
SSH_B=(ssh -i "$APPLIANCE_KEY" -o BatchMode=yes -o StrictHostKeyChecking=no "${APPLIANCE_USER}@${NODE_B_IP}")

log() { echo "[kb115-provision] $*"; }

wait_ssh() {
  local ip="$1"
  local i
  for i in $(seq 1 60); do
    if ssh -i "$APPLIANCE_KEY" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=no \
      "${APPLIANCE_USER}@${ip}" 'echo ok' >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  return 1
}

use_alias_mode() {
  HA_MODE="alias"
  NODE_A_IP="${SOVEREIGN_HA_NODE_A_IP:-192.168.0.231}"
  NODE_B_IP="${SOVEREIGN_HA_NODE_B_IP:-192.168.0.232}"
  log "Using alias HA mode on Beta ${BETA_HOST} (${NODE_A_IP} + ${NODE_B_IP})"
  bash scripts/kb115_setup_beta_ha_aliases.sh
  APPLIANCE_SSH_KEY="$APPLIANCE_KEY" \
    kevantic-appliance/scripts/enable_sovereign_multihost_cluster_on_appliance.sh \
    "$BETA_HOST" "$APPLIANCE_USER"
  CLUSTER_ID="${SOVEREIGN_CLUSTER_ID:-$(uuidgen 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())')}"
  JOIN_TOKEN="${SOVEREIGN_JOIN_TOKEN:-kb115-$(date +%s)}"

  # Node A agent on alias IP
  "${SSH_BETA[@]}" "sudo -n bash -s" <<REMOTE
set -euo pipefail
export SOVEREIGN_CLUSTER_TOPOLOGY=multihost
export SOVEREIGN_NODE_ID=a SOVEREIGN_LOCAL_HOST=${NODE_A_IP} SOVEREIGN_PEER_HOST=${NODE_B_IP}
export SOVEREIGN_PEER_NODE_ID=b SOVEREIGN_CLUSTER_ID=${CLUSTER_ID} SOVEREIGN_JOIN_TOKEN=${JOIN_TOKEN}
sovereign-multihost-cluster pair
pkill -f 'node_agent --node-id a' 2>/dev/null || true
pkill -f 'node_agent --node-id b' 2>/dev/null || true
nohup env SOVEREIGN_CLUSTER_TOPOLOGY=multihost PYTHONPATH=/opt/junexis/appliance-src:/opt/kevantic/appliance-src python3 -m appliance.sovereign.node_agent \
  --node-id a --port 8443 --bind ${NODE_A_IP} >/var/log/sovereign-mh-a.log 2>&1 &
echo \$! >/run/sovereign-multihost/node-a.pid
REMOTE

  # Node B agent on second alias IP
  "${SSH_BETA[@]}" "sudo -n bash -s" <<REMOTE
set -euo pipefail
export SOVEREIGN_CLUSTER_TOPOLOGY=multihost
export SOVEREIGN_NODE_ID=b SOVEREIGN_LOCAL_HOST=${NODE_B_IP} SOVEREIGN_PEER_HOST=${NODE_A_IP}
export SOVEREIGN_PEER_NODE_ID=a SOVEREIGN_CLUSTER_ID=${CLUSTER_ID} SOVEREIGN_JOIN_TOKEN=${JOIN_TOKEN}
sovereign-multihost-cluster pair
nohup env SOVEREIGN_CLUSTER_TOPOLOGY=multihost PYTHONPATH=/opt/junexis/appliance-src:/opt/kevantic/appliance-src python3 -m appliance.sovereign.node_agent \
  --node-id b --port 8443 --bind ${NODE_B_IP} >/var/log/sovereign-mh-b.log 2>&1 &
echo \$! >/run/sovereign-multihost/node-b.pid
REMOTE
  sleep 3
  export SOVEREIGN_HA_NODE_A_IP="$NODE_A_IP" SOVEREIGN_HA_NODE_B_IP="$NODE_B_IP"
  bash scripts/kb115_validate_sovereign_ephemeral_ha.sh
  log "DONE: Alias-mode 2-IP HA sign-off on ${BETA_HOST}"
  exit 0
}

if [[ "$HA_MODE" == "alias" ]]; then
  use_alias_mode
fi

provision_node() {
  local host="$1"
  log "Provisioning sovereign baseline on ${host}"
  APPLIANCE_SSH_HOST="$host" APPLIANCE_SSH_KEY="$APPLIANCE_KEY" \
    bash scripts/kb112_provision_sovereign_beta_lab.sh
  APPLIANCE_SSH_KEY="$APPLIANCE_KEY" \
    kevantic-appliance/scripts/enable_sovereign_multihost_cluster_on_appliance.sh "$host" "$APPLIANCE_USER"
  APPLIANCE_SSH_KEY="$APPLIANCE_KEY" SOVEREIGN_FULL_STACK_MODE=stub \
    kevantic-appliance/scripts/enable_sovereign_full_stack_on_appliance.sh "$host" "$APPLIANCE_USER"
}

if [[ "$SKIP_CLONE" != "1" ]]; then
  log "1/6 Clone ephemeral HA nodes from VM ${SOURCE_VMID}"
  for spec in "${NODE_A_VMID}:${NODE_A_IP}:sovereign-ha-ephemeral-a" "${NODE_B_VMID}:${NODE_B_IP}:sovereign-ha-ephemeral-b"; do
    vmid="${spec%%:*}"
    rest="${spec#*:}"
    ip="${rest%%:*}"
    name="${rest##*:}"
    if ! "${PVE[@]}" "qm status ${vmid}" >/dev/null 2>&1; then
      "${PVE[@]}" "qm clone ${SOURCE_VMID} ${vmid} --name ${name} --full --storage local-zfs"
      "${PVE[@]}" "qm set ${vmid} --ipconfig0 ip=${ip}/24,gw=192.168.0.1"
      "${PVE[@]}" "qm cloudinit update ${vmid}"
    else
      log "VM ${vmid} exists — reusing"
      "${PVE[@]}" "qm set ${vmid} --ipconfig0 ip=${ip}/24,gw=192.168.0.1" || true
      "${PVE[@]}" "qm cloudinit update ${vmid}" || true
    fi
    status="$("${PVE[@]}" "qm status ${vmid}" | awk '{print $2}')"
    [[ "$status" == "running" ]] || "${PVE[@]}" "qm start ${vmid}"
    "${PVE[@]}" "qm reboot ${vmid}" || true
    sleep 15
  done
else
  log "1/6 SKIP clone (SOVEREIGN_HA_SKIP_CLONE=1)"
fi

log "2/6 Wait for SSH on ${NODE_A_IP} and ${NODE_B_IP}"
if ! wait_ssh "$NODE_A_IP" || ! wait_ssh "$NODE_B_IP"; then
  log "WARN: ephemeral clone SSH unavailable — falling back to alias mode on Beta"
  use_alias_mode
fi

log "3/6 Provision sovereign stack on both nodes"
chmod +x kevantic-appliance/scripts/enable_sovereign_multihost_cluster_on_appliance.sh \
  kevantic-appliance/scripts/sovereign_multihost_cluster.sh
provision_node "$NODE_A_IP"
provision_node "$NODE_B_IP"

log "4/6 Pair multihost cluster (cluster_id=${CLUSTER_ID})"
"${SSH_A[@]}" "sudo -n env SOVEREIGN_NODE_ID=a SOVEREIGN_LOCAL_HOST=${NODE_A_IP} SOVEREIGN_PEER_HOST=${NODE_B_IP} \
  SOVEREIGN_PEER_NODE_ID=b SOVEREIGN_CLUSTER_ID=${CLUSTER_ID} SOVEREIGN_JOIN_TOKEN=${JOIN_TOKEN} \
  sovereign-multihost-cluster pair"
"${SSH_B[@]}" "sudo -n env SOVEREIGN_NODE_ID=b SOVEREIGN_LOCAL_HOST=${NODE_B_IP} SOVEREIGN_PEER_HOST=${NODE_A_IP} \
  SOVEREIGN_PEER_NODE_ID=a SOVEREIGN_CLUSTER_ID=${CLUSTER_ID} SOVEREIGN_JOIN_TOKEN=${JOIN_TOKEN} \
  sovereign-multihost-cluster pair"

log "5/6 Start node agents"
"${SSH_A[@]}" 'sudo -n env SOVEREIGN_NODE_ID=a sovereign-multihost-cluster start'
"${SSH_B[@]}" 'sudo -n env SOVEREIGN_NODE_ID=b sovereign-multihost-cluster start'
sleep 3

log "6/6 Validate ephemeral 2-VM HA"
export SOVEREIGN_HA_NODE_A_IP SOVEREIGN_HA_NODE_B_IP APPLIANCE_SSH_KEY="$APPLIANCE_KEY"
bash scripts/kb115_validate_sovereign_ephemeral_ha.sh

log "DONE: Ephemeral 2-VM HA provisioned (${NODE_A_IP} + ${NODE_B_IP})"
