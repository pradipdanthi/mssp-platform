#!/usr/bin/env bash
# Create Proxmox VM 110 (velociraptor) from Ubuntu 24.04 cloud image.
# Idempotent: skips create if VMID 110 already exists.
set -euo pipefail

PROXMOX_HOST="${PROXMOX_HOST:-192.168.0.191}"
SSH_KEY="${PROXMOX_SSH_KEY:-$HOME/.ssh/id_ed25519_proxmox}"
VMID=110
NAME=velociraptor
IP=192.168.0.220
GW=192.168.0.1
PUBKEY_FILE="${VELOCIRAPTOR_PUBKEY:-$HOME/.ssh/id_ed25519_velociraptor.pub}"

if [[ ! -f "$PUBKEY_FILE" ]]; then
  echo "Missing pubkey: $PUBKEY_FILE" >&2
  exit 1
fi

scp -i "$SSH_KEY" -o BatchMode=yes "$PUBKEY_FILE" "root@${PROXMOX_HOST}:/tmp/mssp-vr-110.pub"

ssh -i "$SSH_KEY" -o BatchMode=yes "root@${PROXMOX_HOST}" bash -s <<'EOF'
set -euo pipefail
VMID=110
NAME=velociraptor
IP=192.168.0.220
GW=192.168.0.1

if qm status "$VMID" >/dev/null 2>&1; then
  echo "VM $VMID already exists"
  qm status "$VMID"
  exit 0
fi

IMG=/var/lib/vz/template/iso/ubuntu-24.04-server-cloudimg-amd64.img
if [[ ! -f "$IMG" ]]; then
  echo "Cloud image missing: $IMG" >&2
  exit 1
fi

qm create "$VMID" \
  --name "$NAME" \
  --memory 8192 \
  --cores 4 \
  --cpu x86-64-v2-AES \
  --net0 virtio,bridge=vmbr0,firewall=1 \
  --ostype l26 \
  --scsihw virtio-scsi-single \
  --agent enabled=1

qm importdisk "$VMID" "$IMG" local-zfs
qm set "$VMID" --scsi0 local-zfs:vm-${VMID}-disk-0,iothread=1
qm resize "$VMID" scsi0 60G
qm set "$VMID" --boot order=scsi0
qm set "$VMID" --ide2 local-zfs:cloudinit
qm set "$VMID" --serial0 socket --vga serial0
qm set "$VMID" --ipconfig0 "ip=${IP}/24,gw=${GW}"
qm set "$VMID" --nameserver 1.1.1.1
qm set "$VMID" --ciuser secadmin
qm set "$VMID" --sshkeys /tmp/mssp-vr-110.pub
PASS="$(openssl rand -base64 18)"
qm set "$VMID" --cipassword "$PASS"
qm start "$VMID"
echo "Started VM $VMID $NAME $IP"
qm status "$VMID"
EOF

chmod +x /opt/mssp-control/scripts/kb110_create_velociraptor_vm.sh 2>/dev/null || true
