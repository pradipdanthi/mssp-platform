#!/usr/bin/env bash
# KB-115: Destroy ephemeral sovereign HA VMs (221/222 by default).
set -euo pipefail

PVE_HOST="${KEVANTIC_PVE_HOST:-192.168.0.191}"
PVE_KEY="${KEVANTIC_PVE_SSH_KEY:-$HOME/.ssh/id_ed25519_proxmox}"
NODE_A_VMID="${SOVEREIGN_HA_NODE_A_VMID:-221}"
NODE_B_VMID="${SOVEREIGN_HA_NODE_B_VMID:-222}"

PVE=(ssh -o BatchMode=yes -i "$PVE_KEY" "root@${PVE_HOST}")

for vmid in "$NODE_A_VMID" "$NODE_B_VMID"; do
  if "${PVE[@]}" "qm status ${vmid}" >/dev/null 2>&1; then
    echo "[kb115-teardown] destroying VM ${vmid}"
    "${PVE[@]}" "qm stop ${vmid} --timeout 30" 2>/dev/null || true
    "${PVE[@]}" "qm destroy ${vmid} --purge 1" || true
  else
    echo "[kb115-teardown] VM ${vmid} not present — skip"
  fi
done

echo "[kb115-teardown] DONE"
