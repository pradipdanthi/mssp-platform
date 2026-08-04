#!/usr/bin/env bash
# Fetch Ubuntu 24.04 live-server ISO + SHA256SUMS into junexis-appliance/.cache
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="$ROOT/.cache"
ISO_NAME="${JUNEXIS_UBUNTU_ISO_NAME:-ubuntu-24.04.4-live-server-amd64.iso}"
BASE_URL="${JUNEXIS_UBUNTU_BASE_URL:-https://releases.ubuntu.com/24.04}"

mkdir -p "$CACHE"
cd "$CACHE"

if [[ ! -f SHA256SUMS ]]; then
  curl -fsSL -o SHA256SUMS "$BASE_URL/SHA256SUMS"
fi

if [[ -f "$ISO_NAME" ]]; then
  echo "ISO already present: $CACHE/$ISO_NAME"
else
  echo "Downloading $ISO_NAME ..."
  wget -c -O "$ISO_NAME.partial" "$BASE_URL/$ISO_NAME"
  mv "$ISO_NAME.partial" "$ISO_NAME"
fi

echo "Verifying checksum..."
grep " $ISO_NAME\$\\|\\*$ISO_NAME\$" SHA256SUMS | sha256sum -c -
echo "OK: $CACHE/$ISO_NAME"
