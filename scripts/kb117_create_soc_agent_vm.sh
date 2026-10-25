#!/usr/bin/env bash
# Create Proxmox VM 117 (mssp-soc-agent) from Ubuntu 24.04 cloud image.
# Idempotent: skips create if VMID 117 already exists.
set -euo pipefail

PROXMOX_HOST="${PROXMOX_HOST:-192.168.0.191}"
SSH_KEY="${PROXMOX_SSH_KEY:-$HOME/.ssh/id_ed25519_proxmox}"
VMID="${SOC_AGENT_VMID:-117}"
NAME="${SOC_AGENT_NAME:-mssp-soc-agent}"
IP="${SOC_AGENT_IP:-192.168.0.228}"
GW="${SOC_AGENT_GW:-192.168.0.1}"
# Host often has <8 GB free; default 6144 so start succeeds. Override SOC_AGENT_MEMORY_MB=8192 when RAM frees up.
MEMORY_MB="${SOC_AGENT_MEMORY_MB:-6144}"
CORES="${SOC_AGENT_CORES:-4}"
DISK_GB="${SOC_AGENT_DISK_GB:-50}"
PUBKEY_FILE="${SOC_AGENT_PUBKEY:-$HOME/.ssh/id_ed25519_soc_agent.pub}"

if [[ ! -f "$PUBKEY_FILE" ]]; then
  echo "Missing pubkey: $PUBKEY_FILE" >&2
  exit 1
fi

scp -i "$SSH_KEY" -o BatchMode=yes "$PUBKEY_FILE" "root@${PROXMOX_HOST}:/tmp/mssp-soc-agent-${VMID}.pub"

ssh -i "$SSH_KEY" -o BatchMode=yes "root@${PROXMOX_HOST}" \
  env VMID="$VMID" NAME="$NAME" IP="$IP" GW="$GW" MEMORY_MB="$MEMORY_MB" CORES="$CORES" DISK_GB="$DISK_GB" \
  bash -s <<'EOF'
set -euo pipefail

if qm status "$VMID" >/dev/null 2>&1; then
  echo "VM $VMID already exists"
  qm status "$VMID"
  qm config "$VMID" | grep -E '^(name|net0|ipconfig0|memory|cores|scsi0)=' || true
  exit 0
fi

IMG=/var/lib/vz/template/iso/ubuntu-24.04-server-cloudimg-amd64.img
if [[ ! -f "$IMG" ]]; then
  echo "Cloud image missing: $IMG" >&2
  exit 1
fi

qm create "$VMID" \
  --name "$NAME" \
  --memory "$MEMORY_MB" \
  --cores "$CORES" \
  --cpu x86-64-v2-AES \
  --net0 virtio,bridge=vmbr0,firewall=0 \
  --ostype l26 \
  --scsihw virtio-scsi-single \
  --agent enabled=1

qm importdisk "$VMID" "$IMG" local-zfs
qm set "$VMID" --scsi0 local-zfs:vm-${VMID}-disk-0,iothread=1
qm resize "$VMID" scsi0 "${DISK_GB}G"
qm set "$VMID" --boot order=scsi0
qm set "$VMID" --ide2 local-zfs:cloudinit
qm set "$VMID" --serial0 socket --vga serial0
qm set "$VMID" --ipconfig0 "ip=${IP}/24,gw=${GW}"
qm set "$VMID" --nameserver 1.1.1.1
qm set "$VMID" --ciuser secadmin
qm set "$VMID" --sshkeys "/tmp/mssp-soc-agent-${VMID}.pub"
qm set "$VMID" --ciupgrade 0
qm set "$VMID" --vga std
PASS="$(openssl rand -base64 18)"
qm set "$VMID" --cipassword "$PASS"
qm start "$VMID"
echo "Started VM $VMID $NAME $IP memory=${MEMORY_MB}M cores=$CORES disk=${DISK_GB}G"
qm status "$VMID"
EOF

echo "OK: VM $VMID -> $IP"
