#!/usr/bin/env bash
# Create permanent Proxmox VM 114 — Junexis Appliance Management plane.
# Hosts appliance channel gateway (not co-located on mssp-control / VM 100).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PVE_HOST="${JUNEXIS_PVE_HOST:-192.168.0.191}"
PVE_KEY="${JUNEXIS_PVE_SSH_KEY:-$HOME/.ssh/id_ed25519_proxmox}"
PVE_SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$PVE_KEY" "root@${PVE_HOST}")
VMID="${JUNEXIS_MGMT_VMID:-114}"
VM_NAME="${JUNEXIS_MGMT_VM_NAME:-junexis-appliance-mgmt}"
VM_IP="${JUNEXIS_MGMT_VM_IP:-192.168.0.224}"
VM_CIDR="${JUNEXIS_MGMT_VM_CIDR:-24}"
VM_GW="${JUNEXIS_MGMT_VM_GW:-192.168.0.1}"
VM_MEM="${JUNEXIS_MGMT_VM_MEM:-4096}"
VM_CORES="${JUNEXIS_MGMT_VM_CORES:-2}"
VM_DISK="${JUNEXIS_MGMT_VM_DISK:-40}"
BRIDGE="${JUNEXIS_MGMT_VM_BRIDGE:-vmbr0}"
STORAGE="${JUNEXIS_MGMT_VM_STORAGE:-local-zfs}"
CLOUDIMG="${JUNEXIS_BUILD_CLOUDIMG:-/var/lib/vz/template/iso/ubuntu-24.04-server-cloudimg-amd64.img}"
# Reuse factory build pubkey for bootstrap; rotate later in production
SSH_PUB="${JUNEXIS_MGMT_SSH_PUB:-$ROOT/junexis-appliance/.tools/build-ssh/junexis_packer.pub}"
CI_USER="${JUNEXIS_MGMT_CI_USER:-junexis}"
CI_PASS="${JUNEXIS_MGMT_CI_PASS:-JunexisMgmtChangeMe}"

if [[ ! -f "$SSH_PUB" ]]; then
  echo "Missing SSH pubkey: $SSH_PUB" >&2
  exit 2
fi
if [[ ! -f "$PVE_KEY" ]]; then
  echo "Missing Proxmox SSH key: $PVE_KEY" >&2
  exit 2
fi

echo "Creating Appliance Management VM ${VMID} (${VM_NAME}) IP ${VM_IP} on ${PVE_HOST}..."
scp -o BatchMode=yes -i "$PVE_KEY" "$SSH_PUB" "root@${PVE_HOST}:/tmp/junexis_mgmt_vm.pub"

"${PVE_SSH[@]}" bash -s <<EOF
set -euo pipefail
VMID=$VMID
if qm status "\$VMID" >/dev/null 2>&1; then
  echo "VM \$VMID already exists — leaving in place"
  qm status "\$VMID"
  qm config "\$VMID" | egrep 'name:|memory:|ipconfig0:|net0:' || true
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
  --onboot 1 \\
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
qm set "\$VMID" --sshkeys /tmp/junexis_mgmt_vm.pub
qm set "\$VMID" --ciupgrade 0
rm -f /tmp/junexis_mgmt_vm.pub

qm start "\$VMID"
qm status "\$VMID"
echo APPLIANCE_MGMT_VM_CREATED
EOF

echo "Waiting for SSH on ${VM_IP}..."
SSH_PRIV="${SSH_PUB%.pub}"
ssh-keygen -R "${VM_IP}" >/dev/null 2>&1 || true
for i in $(seq 1 90); do
  if ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null \
      -o ConnectTimeout=5 \
      -i "$SSH_PRIV" -o IdentitiesOnly=yes \
      "${CI_USER}@${VM_IP}" 'echo SSH_OK; hostname; free -h | head -2' 2>/dev/null; then
    echo APPLIANCE_MGMT_VM_READY
    exit 0
  fi
  sleep 5
done

echo "VM created but SSH not ready yet on ${VM_IP}." >&2
exit 4
