#!/usr/bin/env bash
# Remove ephemeral HA lab IPs from Beta.
set -euo pipefail

BETA_HOST="${APPLIANCE_SSH_HOST:-192.168.0.226}"
NODE_A_IP="${SOVEREIGN_HA_NODE_A_IP:-192.168.0.231}"
NODE_B_IP="${SOVEREIGN_HA_NODE_B_IP:-192.168.0.232}"
APPLIANCE_USER="${APPLIANCE_SSH_USER:-junexis}"
APPLIANCE_KEY="${APPLIANCE_SSH_KEY:-/opt/mssp-control/kevantic-appliance/.tools/build-ssh/kevantic_packer}"

ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o BatchMode=yes \
  "${APPLIANCE_USER}@${BETA_HOST}" \
  "sudo -n bash -s" <<REMOTE
set -euo pipefail
for nid in a b; do
  env SOVEREIGN_NODE_ID="\${nid}" sovereign-multihost-cluster stop 2>/dev/null || true
done
pkill -f "appliance.sovereign.node_agent --node-id" 2>/dev/null || true
for ip in ${NODE_A_IP} ${NODE_B_IP}; do
  ip addr del "\${ip}/24" dev \$(ip -o -4 addr show | awk -v ip="\${ip}" '\$0 ~ ip {print \$2; exit}') 2>/dev/null || true
  ip addr del "\${ip}/32" dev lo 2>/dev/null || true
done
REMOTE

echo "[kb115-alias] removed aliases ${NODE_A_IP} ${NODE_B_IP} from ${BETA_HOST}"
