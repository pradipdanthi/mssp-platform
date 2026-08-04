#!/usr/bin/env bash
# Export Proxmox build VM disk to versioned Junexis field artifacts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PVE_HOST="${JUNEXIS_PVE_HOST:-192.168.0.191}"
PVE_KEY="${JUNEXIS_PVE_SSH_KEY:-$HOME/.ssh/id_ed25519_proxmox}"
PVE_SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$PVE_KEY" "root@${PVE_HOST}")
VMID="${JUNEXIS_BUILD_VMID:-113}"
VER="$(tr -d '[:space:]' < "$ROOT/VERSION")"
DIST="$ROOT/.cache/dist"
NAME="Junexis-Appliance-v${VER}"
STAGE_REMOTE="/var/tmp/junexis-export-${VMID}"

mkdir -p "$DIST"

echo "Stopping VM ${VMID} for consistent export..."
"${PVE_SSH[@]}" "qm shutdown ${VMID} --timeout 120 || qm stop ${VMID}; sleep 2; qm status ${VMID}"

echo "Exporting scsi0 to qcow2 on Proxmox..."
"${PVE_SSH[@]}" bash -s <<EOF
set -euo pipefail
VMID=$VMID
STAGE='$STAGE_REMOTE'
NAME='$NAME'
rm -rf "\$STAGE"
mkdir -p "\$STAGE"
DISK=\$(qm config "\$VMID" | awk -F': ' '/^scsi0: /{print \$2}' | cut -d, -f1)
VOLNAME=\${DISK#*:}
ZVOL="/dev/zvol/rpool/data/\${VOLNAME}"
if [[ ! -e "\$ZVOL" ]]; then
  ZVOL=\$(find /dev/zvol -name "vm-\${VMID}-disk-0" 2>/dev/null | head -1 || true)
fi
if [[ -z "\${ZVOL:-}" || ! -e "\$ZVOL" ]]; then
  echo "Cannot locate zvol for disk=\$DISK" >&2
  ls -la /dev/zvol/rpool/data/ 2>/dev/null | head >&2 || true
  exit 3
fi
echo "Using \$ZVOL"
qemu-img convert -p -f raw -O qcow2 "\$ZVOL" "\$STAGE/\${NAME}.qcow2"
qemu-img convert -p -f qcow2 -O raw "\$STAGE/\${NAME}.qcow2" "\$STAGE/\${NAME}.raw"
ls -lh "\$STAGE"
EOF

echo "Pulling artifacts to $DIST ..."
scp -o BatchMode=yes -i "$PVE_KEY" \
  "root@${PVE_HOST}:${STAGE_REMOTE}/${NAME}.qcow2" \
  "root@${PVE_HOST}:${STAGE_REMOTE}/${NAME}.raw" \
  "$DIST/"

STAGE_ISO="$DIST/_iso_stage"
rm -rf "$STAGE_ISO"
mkdir -p "$STAGE_ISO"
cp -f "$DIST/${NAME}.qcow2" "$DIST/${NAME}.raw" "$STAGE_ISO/"
cat > "$STAGE_ISO/README.txt" <<EOF
Junexis Appliance v${VER}
========================
Built on Proxmox factory VM ${VMID} (not nested Packer on VM 100).
Single appliance image (minimize, junexis-cli, DuckDB/Parquet engine,
anonymizing telemetry, retrospective hunt). No TheHive on appliance.

Virtual deploy: import ${NAME}.qcow2 into Proxmox/ESXi/Hyper-V/KVM.
Bare metal:    sudo dd if=${NAME}.raw of=/dev/DISK bs=4M status=progress conv=fsync

First boot: junexis-cli setup → bootstrap update → network lock
EOF

if command -v genisoimage >/dev/null; then
  genisoimage -V "JUNEXIS_APPLIANCE" -J -r -o "$DIST/${NAME}.iso" "$STAGE_ISO"
elif command -v mkisofs >/dev/null; then
  mkisofs -V "JUNEXIS_APPLIANCE" -J -r -o "$DIST/${NAME}.iso" "$STAGE_ISO"
else
  docker run --rm -v "$DIST:/d" -w /d ubuntu:24.04 bash -lc \
    "apt-get update -qq && apt-get install -y -qq genisoimage >/dev/null && genisoimage -V JUNEXIS_APPLIANCE -J -r -o /d/${NAME}.iso /d/_iso_stage"
fi
rm -rf "$STAGE_ISO"

(
  cd "$DIST"
  sha256sum "${NAME}.qcow2" "${NAME}.raw" "${NAME}.iso" > SHA256SUMS
)

"${PVE_SSH[@]}" "rm -rf '${STAGE_REMOTE}'" || true

echo "Published artifacts in $DIST:"
ls -lh "$DIST"
echo B2_PROXMOX_EXPORT_OK
