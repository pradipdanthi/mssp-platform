#!/usr/bin/env bash
# Build a *bootable Ubuntu autoinstall ISO* for the Junexis appliance (customer media).
# This is NOT a qcow2 delivery disc — it boots Subiquity and installs the OS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="$(tr -d '[:space:]' < "$ROOT/VERSION")"
CACHE="$ROOT/.cache"
ISO_IN="${JUNEXIS_UBUNTU_ISO:-$CACHE/ubuntu-24.04.4-live-server-amd64.iso}"
OUT_DIR="$CACHE/dist-install"
OUT_ISO="$OUT_DIR/Junexis-Appliance-Install-v${VER}.iso"
WORK="$CACHE/iso-work"
BUILDER_IMAGE="${JUNEXIS_B2_BUILDER_IMAGE:-junexis-appliance-b2-builder:local}"

if [[ ! -f "$ISO_IN" ]]; then
  echo "Missing Ubuntu ISO: $ISO_IN" >&2
  echo "Run: $ROOT/scripts/b2_fetch_ubuntu_iso.sh" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"
# Prior remaster may leave root-owned extract trees — clean via Docker.
if [[ -d "$WORK" ]]; then
  docker run --rm -v "$WORK:/work" "$BUILDER_IMAGE" bash -c 'rm -rf /work/*' 2>/dev/null \
    || docker run --rm -v "$WORK:/work" ubuntu:24.04 bash -c 'rm -rf /work/*' 2>/dev/null \
    || true
  rm -rf "$WORK" 2>/dev/null || true
fi
mkdir -p "$WORK/seed/junexis-payload"

cp -f "$ROOT/iso/autoinstall/user-data" "$WORK/seed/user-data"
cp -f "$ROOT/iso/autoinstall/meta-data" "$WORK/seed/meta-data"

echo "Staging Junexis payload ..."
# Include channel/ + ota/ source trees (Track-4) so firstboot roles can install them.
# Lab control-plane defaults (VM 114) live under ansible/group_vars + cli + configs/.
tar -C "$ROOT" \
  --exclude='.cache' \
  --exclude='.tools' \
  --exclude='packer' \
  --exclude='**/__pycache__' \
  --exclude='**/*.pyc' \
  -cf - \
  ansible services hardening cli configs licensing appliance engines channel ota \
  requirements-engine.txt VERSION docs/SERVICE_MATRIX.md \
  | tar -C "$WORK/seed/junexis-payload" -xf -

cp -f "$ROOT/iso/firstboot/junexis-firstboot.sh" "$WORK/seed/junexis-payload/junexis-firstboot.sh"
cp -f "$ROOT/iso/firstboot/junexis-firstboot.service" "$WORK/seed/junexis-payload/junexis-firstboot.service"
chmod +x "$WORK/seed/junexis-payload/junexis-firstboot.sh" "$ROOT/iso/docker_remaster.sh"

# Airgap engine .debs + binaries + wheels
OFFLINE_SRC="$ROOT/iso/offline-packages"
if compgen -G "$OFFLINE_SRC/*.deb" >/dev/null; then
  echo "Staging offline engine packages ($(find "$OFFLINE_SRC" -maxdepth 1 -name '*.deb' | wc -l) debs) ..."
  mkdir -p "$WORK/seed/junexis-payload/offline-packages/bin" "$WORK/seed/junexis-payload/offline-packages/wheels"
  cp -a "$OFFLINE_SRC"/*.deb "$WORK/seed/junexis-payload/offline-packages/"
  [[ -d "$OFFLINE_SRC/bin" ]] && cp -a "$OFFLINE_SRC/bin/." "$WORK/seed/junexis-payload/offline-packages/bin/" || true
  [[ -d "$OFFLINE_SRC/wheels" ]] && cp -a "$OFFLINE_SRC/wheels/." "$WORK/seed/junexis-payload/offline-packages/wheels/" || true
  [[ -f "$OFFLINE_SRC/SHA256SUMS" ]] && cp -f "$OFFLINE_SRC/SHA256SUMS" "$WORK/seed/junexis-payload/offline-packages/"
  [[ -f "$OFFLINE_SRC/MANIFEST.txt" ]] && cp -f "$OFFLINE_SRC/MANIFEST.txt" "$WORK/seed/junexis-payload/offline-packages/"
else
  echo "WARN: no .deb files in $OFFLINE_SRC — firstboot will need bootstrap Internet for engines." >&2
  echo "      Run: $ROOT/scripts/b2_fetch_offline_packages.sh" >&2
fi

if [[ -f "$ROOT/licensing/keys/licensing-ed25519-v1.pub" ]]; then
  mkdir -p "$WORK/seed/junexis-payload/licensing/keys"
  cp -f "$ROOT/licensing/keys/licensing-ed25519-v1.pub" \
    "$WORK/seed/junexis-payload/licensing/keys/"
fi

if ! docker image inspect "$BUILDER_IMAGE" >/dev/null 2>&1; then
  echo "Builder image missing — building $BUILDER_IMAGE ..."
  "$ROOT/scripts/b2_build_builder_image.sh"
fi

echo "Remastering ISO via Docker ($BUILDER_IMAGE) ..."
docker run --rm \
  -v "$ISO_IN:/in.iso:ro" \
  -v "$WORK:/work" \
  -v "$ROOT/iso/docker_remaster.sh:/remaster.sh:ro" \
  "$BUILDER_IMAGE" \
  bash /remaster.sh /in.iso /work

if [[ ! -f "$WORK/Junexis-Appliance-Install.iso" ]]; then
  echo "ISO build failed — output missing" >&2
  exit 3
fi

cp -f "$WORK/Junexis-Appliance-Install.iso" "$OUT_ISO"
(
  cd "$OUT_DIR"
  sha256sum "$(basename "$OUT_ISO")" > SHA256SUMS
)
ls -lh "$OUT_ISO"
cat "$OUT_DIR/SHA256SUMS"
echo "B2_INSTALL_ISO_OK path=$OUT_ISO"
echo "Boot this ISO in VM / bare metal / cloud to install the appliance OS."
