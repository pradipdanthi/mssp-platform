#!/usr/bin/env bash
# After Packer succeeds: version + publish field artifacts (qcow2, raw, checksums).
# Bare metal: dd the .raw to disk/USB. Virtual: import .qcow2 (Proxmox/ESXi/Hyper-V via convert).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/.cache/output/junexis-appliance-qcow2}"
VER="$(tr -d '[:space:]' < "$ROOT/VERSION")"
DIST="$ROOT/.cache/dist"
mkdir -p "$DIST"

QCOW=$(find "$OUT" -type f \( -name '*.qcow2' -o -name 'junexis-appliance*' \) 2>/dev/null | head -1 || true)
if [[ -z "${QCOW}" ]]; then
  echo "No qcow2 found under $OUT" >&2
  find "$OUT" -type f 2>/dev/null | head -50 >&2 || true
  exit 2
fi

NAME="Junexis-Appliance-v${VER}"
cp -f "$QCOW" "$DIST/${NAME}.qcow2"

if command -v qemu-img >/dev/null; then
  qemu-img convert -f qcow2 -O raw "$DIST/${NAME}.qcow2" "$DIST/${NAME}.raw"
elif docker image inspect junexis-appliance-b2-builder:local >/dev/null 2>&1; then
  docker run --rm -v "$DIST:/d" junexis-appliance-b2-builder:local \
    qemu-img convert -f qcow2 -O raw "/d/${NAME}.qcow2" "/d/${NAME}.raw"
else
  echo "qemu-img not available — skipping raw convert" >&2
fi

# Lightweight delivery ISO: contains qcow2 + README (engineers extract or use with virt).
# Not a live installer; bare-metal path remains dd of .raw.
if command -v genisoimage >/dev/null || command -v mkisofs >/dev/null || docker image inspect junexis-appliance-b2-builder:local >/dev/null 2>&1; then
  STAGE="$DIST/_iso_stage"
  rm -rf "$STAGE"
  mkdir -p "$STAGE"
  cp -f "$DIST/${NAME}.qcow2" "$STAGE/"
  [[ -f "$DIST/${NAME}.raw" ]] && cp -f "$DIST/${NAME}.raw" "$STAGE/" || true
  cat > "$STAGE/README.txt" <<EOF
Junexis Appliance v${VER}
========================
Single appliance image (all features: minimize, junexis-cli, DuckDB/Parquet
engine, anonymizing telemetry, retrospective hunt). No TheHive on appliance.

Virtual deploy: import ${NAME}.qcow2 into Proxmox/ESXi/Hyper-V/KVM.
Bare metal:    sudo dd if=${NAME}.raw of=/dev/DISK bs=4M status=progress conv=fsync

First boot: junexis-cli setup → bootstrap update → network lock
EOF
  if command -v genisoimage >/dev/null; then
    genisoimage -V "JUNEXIS_APPLIANCE" -J -r -o "$DIST/${NAME}.iso" "$STAGE"
  elif command -v mkisofs >/dev/null; then
    mkisofs -V "JUNEXIS_APPLIANCE" -J -r -o "$DIST/${NAME}.iso" "$STAGE"
  else
    docker run --rm -v "$DIST:/d" -w /d ubuntu:24.04 bash -lc \
      "apt-get update -qq && apt-get install -y -qq genisoimage >/dev/null && genisoimage -V JUNEXIS_APPLIANCE -J -r -o /d/${NAME}.iso /d/_iso_stage"
  fi
  rm -rf "$STAGE"
fi

(
  cd "$DIST"
  sha256sum ${NAME}.qcow2 ${NAME}.raw ${NAME}.iso 2>/dev/null > SHA256SUMS || sha256sum ${NAME}.qcow2 > SHA256SUMS
)

echo "Published artifacts in $DIST:"
ls -lh "$DIST"
