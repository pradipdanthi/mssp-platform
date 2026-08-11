#!/usr/bin/env bash
# Create disposable Proxmox build VM 113 — Kevantic immutable image factory (KB-093N).
# Runs mkosi / UKI / verity builds. NEVER use VM 100 or VM 114 for this.
# Does NOT host the Appliance Management channel gateway (that stays on VM 114).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PVE_HOST="${KEVANTIC_PVE_HOST:-192.168.0.191}"
PVE_KEY="${KEVANTIC_PVE_SSH_KEY:-$HOME/.ssh/id_ed25519_proxmox}"
PVE_SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$PVE_KEY" "root@${PVE_HOST}")
VMID="${KEVANTIC_BUILD_VMID:-113}"
VM_NAME="${KEVANTIC_BUILD_VM_NAME:-kevantic-appliance-build}"
VM_IP="${KEVANTIC_BUILD_VM_IP:-192.168.0.223}"
VM_CIDR="${KEVANTIC_BUILD_VM_CIDR:-24}"
VM_GW="${KEVANTIC_BUILD_VM_GW:-192.168.0.1}"
VM_MEM="${KEVANTIC_BUILD_VM_MEM:-8192}"
VM_CORES="${KEVANTIC_BUILD_VM_CORES:-4}"
VM_DISK="${KEVANTIC_BUILD_VM_DISK:-100}"
BRIDGE="${KEVANTIC_BUILD_VM_BRIDGE:-vmbr0}"
STORAGE="${KEVANTIC_BUILD_VM_STORAGE:-local-zfs}"
CLOUDIMG="${KEVANTIC_BUILD_CLOUDIMG:-/var/lib/vz/template/iso/ubuntu-24.04-server-cloudimg-amd64.img}"
SSH_PUB="${KEVANTIC_BUILD_SSH_PUB:-$ROOT/.tools/build-ssh/kevantic_packer.pub}"
CI_USER="${KEVANTIC_BUILD_CI_USER:-kevantic}"
CI_PASS="${KEVANTIC_BUILD_CI_PASS:-KevanticBuildOnlyChangeMe}"

if [[ ! -f "$SSH_PUB" ]]; then
  echo "Missing build SSH pubkey: $SSH_PUB" >&2
  exit 2
fi
if [[ ! -f "$PVE_KEY" ]]; then
  echo "Missing Proxmox SSH key: $PVE_KEY" >&2
  exit 2
fi

echo "Creating/ensuring Proxmox build VM ${VMID} (${VM_NAME}) on ${PVE_HOST}..."

# Upload pubkey for qm --sshkeys
scp -o BatchMode=yes -i "$PVE_KEY" "$SSH_PUB" "root@${PVE_HOST}:/tmp/kevantic_build_vm.pub"

"${PVE_SSH[@]}" bash -s <<EOF
set -euo pipefail
VMID=$VMID
if qm status "\$VMID" >/dev/null 2>&1; then
  echo "VM \$VMID already exists — leaving in place"
  qm status "\$VMID"
  exit 0
fi

CLOUDIMG='$CLOUDIMG'
[[ -f "\$CLOUDIMG" ]] || { echo "Missing \$CLOUDIMG" >&2; exit 2; }

qm create "\$VMID" \\
  --name '$VM_NAME' \\
  --memory '$VM_MEM' \\
  --cores '$VM_CORES' \\
  --sockets 1 \\
  --cpu x86-64-v2-AES \\
  --ostype l26 \\
  --scsihw virtio-scsi-single \\
  --net0 'virtio,bridge=${BRIDGE},firewall=0' \\
  --agent enabled=1 \\
  --onboot 0 \\
  --boot order=scsi0

qm importdisk "\$VMID" "\$CLOUDIMG" '$STORAGE' --format qcow2
DISK=\$(qm config "\$VMID" | awk -F': ' '/^unused[0-9]+: /{print \$2; exit}')
[[ -n "\$DISK" ]] || { echo "No unused disk after import" >&2; qm config "\$VMID"; exit 3; }
qm set "\$VMID" --scsi0 "\${DISK},iothread=1,discard=on"
qm resize "\$VMID" scsi0 '${VM_DISK}G'
qm set "\$VMID" --ide2 '${STORAGE}:cloudinit'
qm set "\$VMID" --serial0 socket --vga serial0
qm set "\$VMID" --ipconfig0 'ip=${VM_IP}/${VM_CIDR},gw=${VM_GW}'
qm set "\$VMID" --nameserver '${VM_GW}'
qm set "\$VMID" --ciuser '${CI_USER}'
qm set "\$VMID" --cipassword '${CI_PASS}'
qm set "\$VMID" --sshkeys /tmp/kevantic_build_vm.pub
qm set "\$VMID" --ciupgrade 0
rm -f /tmp/kevantic_build_vm.pub

qm start "\$VMID"
qm status "\$VMID"
echo B2_PROXMOX_BUILD_VM_CREATED
EOF

echo "Waiting for SSH on ${VM_IP} (cloud-init first boot)..."
SSH_PRIV="${SSH_PUB%.pub}"
ssh-keygen -R "${VM_IP}" >/dev/null 2>&1 || true
for i in $(seq 1 90); do
  if ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null \
      -o ConnectTimeout=5 \
      -i "$SSH_PRIV" -o IdentitiesOnly=yes \
      "${CI_USER}@${VM_IP}" 'echo SSH_OK; hostname' 2>/dev/null; then
    echo B2_PROXMOX_BUILD_VM_READY
    exit 0
  fi
  sleep 5
done

echo "VM created but SSH not ready yet on ${VM_IP}. Check Proxmox console for VM ${VMID}." >&2
exit 4
