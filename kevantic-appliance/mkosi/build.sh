#!/usr/bin/env bash
# KB-093N — Build Kevantic immutable appliance disk image with mkosi (VM 113).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MKOSI_DIR="$ROOT/mkosi"
CACHE="$ROOT/.cache/mkosi"
VERSION="$(tr -d '[:space:]' <"$ROOT/VERSION" 2>/dev/null || echo '0.1.0-dev')"
OUT_NAME="Kevantic-Appliance-Immutable-v${VERSION}"

mkdir -p "$CACHE" "$MKOSI_DIR/mkosi.extra/etc" "$MKOSI_DIR/mkosi.packages"

echo "=== KB-093N mkosi build ${OUT_NAME} on $(hostname) ==="

if ! command -v mkosi >/dev/null 2>&1; then
  echo "ERROR: mkosi not installed" >&2
  exit 2
fi

POOL="$ROOT/iso/offline-packages"
rm -rf "${MKOSI_DIR}/mkosi.packages"
mkdir -p "$MKOSI_DIR/mkosi.packages"
if compgen -G "$POOL/*.deb" >/dev/null 2>&1; then
  echo "Staging offline engine .debs ..."
  shopt -s nullglob
  for d in \
    "$POOL"/wazuh-manager_*.deb \
    "$POOL"/fluent-bit_*.deb \
    "$POOL"/suricata_*.deb \
    "$POOL"/suricata-update_*.deb \
    "$POOL"/zeek-lts-core_*.deb \
    "$POOL"/zeekctl-lts_*.deb \
    "$POOL"/podman_*.deb \
    "$POOL"/crun_*.deb \
    "$POOL"/conmon_*.deb
  do
    [[ -f "$d" ]] || continue
    cp -f "$d" "$MKOSI_DIR/mkosi.packages/"
  done
  echo "Staged $(find "$MKOSI_DIR/mkosi.packages" -name '*.deb' | wc -l) deb(s)"
else
  echo "WARN: no offline-packages — base image only"
fi

chmod +x "$MKOSI_DIR/mkosi.postinst" 2>/dev/null || true

PUBKEY="$ROOT/licensing/keys/licensing-ed25519-v1.pub"
if [[ ! -f "$PUBKEY" ]]; then
  echo "ERROR: missing $PUBKEY — run $ROOT/licensing/generate_dev_keypair.sh" >&2
  exit 2
fi
mkdir -p "$MKOSI_DIR/mkosi.extra/etc/kevantic/trust/keys"
cp -f "$PUBKEY" "$MKOSI_DIR/mkosi.extra/etc/kevantic/trust/keys/licensing-ed25519-v1.pub"
echo "Staged license public key into mkosi.extra"

sudo_run() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif sudo -n true 2>/dev/null; then
    sudo -E "$@"
  else
    # Factory VM cloud-init password (lab only)
    echo 'KevanticBuildOnlyChangeMe' | sudo -S -p '' -E "$@"
  fi
}

cd "$MKOSI_DIR"
# Let conf Output= / ImageVersion= drive names; only force rebuild + output dir
sudo_run mkosi --force --output-dir "$CACHE"

echo "=== outputs in $CACHE ==="
ls -lh "$CACHE" | head -30

# Convert largest raw/disk artifact to qcow2 for Proxmox
RAW=""
for cand in "$CACHE/$OUT_NAME" "$CACHE/${OUT_NAME}.raw" "$CACHE"/Kevantic-Appliance-Immutable*; do
  [[ -f "$cand" ]] || continue
  case "$cand" in
    *.qcow2|*.sha256|*.nspawn|*.efi|*.vmlinuz*|*.initrd*) continue ;;
  esac
  RAW="$cand"
  break
done
# Prefer files that look like disk images (large)
if [[ -z "$RAW" ]]; then
  RAW="$(find "$CACHE" -maxdepth 1 -type f -size +100M ! -name '*.qcow2' | head -1 || true)"
fi

if [[ -n "${RAW:-}" ]] && command -v qemu-img >/dev/null 2>&1; then
  QCOW="$CACHE/${OUT_NAME}.qcow2"
  echo "Converting $RAW → $QCOW"
  sudo_run qemu-img convert -O qcow2 "$RAW" "$QCOW"
  sudo_run chown "$(id -u):$(id -g)" "$QCOW" 2>/dev/null || true
  sha256sum "$QCOW" | tee "$CACHE/SHA256SUMS"
  echo "B093N_MKOSI_OK path=$QCOW"
else
  echo "B093N_MKOSI_OK dir=$CACHE (no large raw found for qcow2 yet)"
fi
