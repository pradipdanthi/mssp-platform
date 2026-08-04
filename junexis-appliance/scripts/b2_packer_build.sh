#!/usr/bin/env bash
# Full B2 Packer QEMU build (disposable guest). Requires KVM + downloaded ISO.
# Runs inside Docker builder; does not modify mssp-control host packages.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${JUNEXIS_B2_BUILDER_IMAGE:-junexis-appliance-b2-builder:local}"
CACHE="$ROOT/.cache"
OUT="$ROOT/.cache/output"
ISO_NAME="${JUNEXIS_UBUNTU_ISO_NAME:-ubuntu-24.04.4-live-server-amd64.iso}"
ISO="$CACHE/$ISO_NAME"

if [[ ! -f "$ISO" ]]; then
  echo "ISO missing — run: $ROOT/scripts/b2_fetch_ubuntu_iso.sh" >&2
  exit 2
fi
if [[ ! -e /dev/kvm ]]; then
  echo "/dev/kvm missing — cannot accelerate guest" >&2
  exit 2
fi

mkdir -p "$OUT"
CHECKSUM="$(grep -E "\\*?${ISO_NAME}\$" "$CACHE/SHA256SUMS" | awk '{print $1}')"

echo "Building Junexis appliance qcow2 via Packer (this can take 20–60+ minutes)..."
# --network host: autoinstall HTTP from Packer must reach the QEMU guest reliably
docker run --rm --privileged --network host \
  --device=/dev/kvm \
  -v "$ROOT:/work" \
  -v "$CACHE:/cache:ro" \
  -v "$OUT:/out" \
  -w /work/packer \
  -e PACKER_LOG="${PACKER_LOG:-1}" \
  "$IMAGE" \
  bash -lc "
    set -euo pipefail
    packer init .
    packer build -force \
      -var-file=vars/b2-docker.pkrvars.hcl \
      -var 'ubuntu_iso_url=file:///cache/${ISO_NAME}' \
      -var 'ubuntu_iso_checksum=sha256:${CHECKSUM}' \
      .
    echo B2_PACKER_BUILD_OK
  "

echo "Artifacts under $OUT"
ls -lah "$OUT" || true
