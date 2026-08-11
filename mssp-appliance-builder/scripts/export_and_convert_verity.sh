#!/usr/bin/env bash
# export_and_convert_verity.sh — Export Proxmox VM/template disk and run dm-verity + UKI.
# Run on a host with: qm/ssh to Proxmox, losetup, veritysetup, systemd-ukify (usually factory VM 113 or Proxmox itself).
#
# Usage:
#   sudo ./export_and_convert_verity.sh --vmid 199 --out ./output-mssp-appliance
#   sudo ./export_and_convert_verity.sh --raw /path/to/disk.raw --out ./output-mssp-appliance

set -euo pipefail

log() { printf '[export_verity] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

VMID=""
RAW_IN=""
OUT_DIR=""
PVE_HOST="${KEVANTIC_PVE_HOST:-192.168.0.191}"
PVE_KEY="${KEVANTIC_PVE_SSH_KEY:-$HOME/.ssh/id_ed25519_proxmox}"
STORAGE="${KEVANTIC_BUILD_VM_STORAGE:-local-zfs}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --vmid) VMID="$2"; shift 2 ;;
    --raw)  RAW_IN="$2"; shift 2 ;;
    --out)  OUT_DIR="$2"; shift 2 ;;
    --pve-host) PVE_HOST="$2"; shift 2 ;;
    *) die "unknown arg: $1" ;;
  esac
done

[[ -n "$OUT_DIR" ]] || die "--out required"
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
RAW="${OUT_DIR}/mssp-appliance.raw"

if [[ -n "$RAW_IN" ]]; then
  [[ -f "$RAW_IN" ]] || die "raw not found: $RAW_IN"
  cp -f "$RAW_IN" "$RAW"
elif [[ -n "$VMID" ]]; then
  [[ -f "$PVE_KEY" ]] || die "missing Proxmox SSH key: $PVE_KEY"
  PVE=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$PVE_KEY" "root@${PVE_HOST}")
  log "Stopping VM/template ${VMID} on ${PVE_HOST} (if running)"
  "${PVE[@]}" "qm status ${VMID} >/dev/null 2>&1 && qm stop ${VMID} --timeout 120 || true"
  log "Exporting disk for VMID ${VMID}"
  # Prefer vzdump-style raw export of scsi0
  "${PVE[@]}" bash -s <<EOF
set -euo pipefail
VMID=${VMID}
DISK=\$(qm config "\$VMID" | awk -F': ' '/^scsi0: /{print \$2}' | cut -d, -f1)
[[ -n "\$DISK" ]] || { echo "no scsi0 on \$VMID" >&2; exit 2; }
# DISK like local-zfs:vm-199-disk-0
VOL=\${DISK#*:}
POOL=\${DISK%%:*}
TMP=/var/tmp/mssp-export-\$VMID.raw
rm -f "\$TMP"
if [[ "\$POOL" == "local-zfs" ]]; then
  zfs list -H -o name | grep -F "\$VOL" | head -1
  # zvol path
  ZVOL=/dev/zvol/\$(zfs list -H -o name | awk -v v="\$VOL" '\$0 ~ v {print; exit}')
  if [[ -z "\$ZVOL" || ! -e "\$ZVOL" ]]; then
    # try conventional naming
    ZVOL=/dev/zvol/${STORAGE}/vm-\${VMID}-disk-0
  fi
  [[ -e "\$ZVOL" ]] || { echo "zvol not found for \$DISK" >&2; ls -l /dev/zvol/${STORAGE}/ 2>/dev/null || true; exit 3; }
  qemu-img convert -p -O raw "\$ZVOL" "\$TMP"
else
  qemu-img convert -p -O raw "/var/lib/vz/images/\${VMID}/\*" "\$TMP" 2>/dev/null \\
    || qm disk import "\$VMID" "\$TMP" "\$POOL" 2>/dev/null \\
    || { echo "unsupported storage export for \$DISK" >&2; exit 4; }
fi
ls -lh "\$TMP"
echo "\$TMP"
EOF
  REMOTE_RAW="$("${PVE[@]}" "ls /var/tmp/mssp-export-${VMID}.raw")"
  log "Fetching ${REMOTE_RAW} → ${RAW}"
  scp -o BatchMode=yes -i "$PVE_KEY" "root@${PVE_HOST}:${REMOTE_RAW}" "$RAW"
  "${PVE[@]}" "rm -f /var/tmp/mssp-export-${VMID}.raw"
else
  die "provide --vmid or --raw"
fi

[[ -f "$RAW" ]] || die "export failed — no $RAW"
export MSSP_RAW_DISK="$RAW"
export MSSP_OUTPUT_DIR="$OUT_DIR"
export MSSP_UKI_OUT="$OUT_DIR/mssp-appliance-uki.efi"
chmod +x "$SCRIPT_DIR/convert_verity.sh"
log "Running convert_verity.sh"
if [[ "$(id -u)" -eq 0 ]]; then
  "$SCRIPT_DIR/convert_verity.sh"
else
  sudo -E "$SCRIPT_DIR/convert_verity.sh"
fi
log "DONE — artifacts in $OUT_DIR"
ls -lh "$OUT_DIR"
exit 0
