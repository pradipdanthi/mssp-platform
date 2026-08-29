#!/usr/bin/env bash
# Add ephemeral HA lab IPs on Beta (192.168.0.227 / .228) for 2-node multihost sign-off.
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
IFACE=\$(ip -o -4 route show to default | awk '{print \$5; exit}')
for ip in ${NODE_A_IP} ${NODE_B_IP}; do
  if ip -o -4 addr show dev "\$IFACE" | grep -q "inet \${ip}/"; then
    echo "alias \${ip} already present on \$IFACE"
  else
    ip addr add "\${ip}/24" dev "\$IFACE" || ip addr add "\${ip}/32" dev lo
    echo "added alias \${ip}"
  fi
done
REMOTE

echo "[kb115-alias] Beta ${BETA_HOST} now answers on ${NODE_A_IP} and ${NODE_B_IP}"
