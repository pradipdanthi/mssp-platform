#!/usr/bin/env bash
# build_golden_cloudimg.sh — Golden appliance build WITHOUT Subiquity ISO.
# Creates ephemeral Proxmox VM from Ubuntu cloud image + cloud-init, then Ansible via VM 112.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PVE_HOST="${KEVANTIC_PVE_HOST:-192.168.0.191}"
PVE_KEY="${KEVANTIC_PVE_SSH_KEY:-$HOME/.ssh/id_ed25519_proxmox}"
PVE_SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$PVE_KEY" "root@${PVE_HOST}")
VMID="${MSSP_GOLDEN_VMID:-199}"
VM_NAME="${MSSP_GOLDEN_VM_NAME:-mssp-appliance-golden-build}"
VM_IP="${MSSP_GOLDEN_VM_IP:-192.168.0.225}"
VM_CIDR="${MSSP_GOLDEN_VM_CIDR:-24}"
VM_GW="${MSSP_GOLDEN_VM_GW:-192.168.0.1}"
VM_MEM="${MSSP_GOLDEN_VM_MEM:-8192}"
VM_CORES="${MSSP_GOLDEN_VM_CORES:-4}"
VM_DISK="${MSSP_GOLDEN_VM_DISK:-64}"
STORAGE="${MSSP_GOLDEN_STORAGE:-local-zfs}"
BRIDGE="${MSSP_GOLDEN_BRIDGE:-vmbr0}"
CLOUDIMG="${MSSP_CLOUDIMG:-/var/lib/vz/template/iso/ubuntu-24.04-server-cloudimg-amd64.img}"
SSH_PUB="${MSSP_BUILD_SSH_PUB:-$ROOT/../kevantic-appliance/.tools/build-ssh/kevantic_packer.pub}"
SSH_PRIV="${SSH_PUB%.pub}"
CI_USER="${MSSP_BUILD_USER:-packer}"
CI_PASS="${MSSP_BUILD_PASS:-PackerBuildOnlyChangeMe!}"
LOG="${ROOT}/.cache/build_golden_cloudimg.log"

mkdir -p "${ROOT}/.cache"
exec > >(tee -a "$LOG") 2>&1

log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }

[[ -f "$SSH_PUB" && -f "$SSH_PRIV" ]] || { log "missing build SSH keys"; exit 2; }
[[ -f "$PVE_KEY" ]] || { log "missing Proxmox key"; exit 2; }

log "Destroying old VM ${VMID} if present"
"${PVE_SSH[@]}" "qm stop ${VMID} --timeout 30 2>/dev/null || true; qm destroy ${VMID} --purge 1 --destroy-unreferenced-disks 1 2>/dev/null || true"

log "Uploading SSH pubkey to Proxmox"
scp -o BatchMode=yes -i "$PVE_KEY" "$SSH_PUB" "root@${PVE_HOST}:/tmp/mssp_golden.pub"

log "Creating VM ${VMID} from cloud image"
"${PVE_SSH[@]}" bash -s <<EOF
set -euo pipefail
[[ -f '${CLOUDIMG}' ]] || { echo "Missing cloud image ${CLOUDIMG}" >&2; exit 2; }
qm create ${VMID} \\
  --name '${VM_NAME}' \\
  --memory ${VM_MEM} \\
  --cores ${VM_CORES} \\
  --cpu host \\
  --ostype l26 \\
  --scsihw virtio-scsi-single \\
  --net0 virtio,bridge=${BRIDGE},firewall=0 \\
  --agent enabled=1 \\
  --onboot 0 \\
  --boot order=scsi0
qm importdisk ${VMID} '${CLOUDIMG}' '${STORAGE}' --format qcow2
DISK=\$(qm config ${VMID} | awk -F': ' '/^unused[0-9]+: /{print \$2; exit}')
qm set ${VMID} --scsi0 "\${DISK},iothread=1,discard=on"
qm resize ${VMID} scsi0 ${VM_DISK}G
qm set ${VMID} --ide2 '${STORAGE}:cloudinit'
qm set ${VMID} --serial0 socket --vga serial0
qm set ${VMID} --ipconfig0 'ip=${VM_IP}/${VM_CIDR},gw=${VM_GW}'
qm set ${VMID} --nameserver '${VM_GW}'
qm set ${VMID} --ciuser '${CI_USER}'
qm set ${VMID} --cipassword '${CI_PASS}'
qm set ${VMID} --sshkeys /tmp/mssp_golden.pub
qm set ${VMID} --ciupgrade 1
rm -f /tmp/mssp_golden.pub
qm start ${VMID}
qm status ${VMID}
EOF

log "Waiting for SSH on ${CI_USER}@${VM_IP} (max 10 min)"
ssh-keygen -R "${VM_IP}" >/dev/null 2>&1 || true
for i in $(seq 1 120); do
  if ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 \
      -i "$SSH_PRIV" -o IdentitiesOnly=yes \
      "${CI_USER}@${VM_IP}" 'echo SSH_OK; hostname' 2>/dev/null; then
    log "SSH ready on ${VM_IP}"
    break
  fi
  if [[ "$i" -eq 120 ]]; then
    log "SSH timeout — check Proxmox console VM ${VMID}"
    exit 3
  fi
  sleep 5
done

log "Running golden Ansible provision via VM 112"
export MSSP_TARGET_HOST="${VM_IP}"
export MSSP_TARGET_USER="${CI_USER}"
export MSSP_TARGET_PASSWORD="${CI_PASS}"
export MSSP_ANSIBLE_CONTROLLER="${MSSP_ANSIBLE_CONTROLLER:-192.168.0.222}"
export MSSP_ANSIBLE_CONTROLLER_USER="${MSSP_ANSIBLE_CONTROLLER_USER:-secadmin}"
export MSSP_ANSIBLE_CONTROLLER_KEY="${MSSP_ANSIBLE_CONTROLLER_KEY:-$HOME/.ssh/id_ed25519_automation}"
export MSSP_BUILDER_ROOT="${ROOT}"
chmod +x "${ROOT}/scripts/provision_via_vm112.sh"
"${ROOT}/scripts/provision_via_vm112.sh"

log "Shutting down VM ${VMID} after provision"
"${PVE_SSH[@]}" "qm shutdown ${VMID} --timeout 120 || qm stop ${VMID} --timeout 60"
sleep 5
"${PVE_SSH[@]}" "qm status ${VMID}"

log "GOLDEN_CLOUDIMG_BUILD_OK — next: export/template VM ${VMID} or run export_and_convert_verity.sh"
echo GOLDEN_CLOUDIMG_BUILD_OK | tee "${ROOT}/.cache/GOLDEN_BUILD_OK"
