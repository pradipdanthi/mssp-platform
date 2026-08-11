#!/usr/bin/env bash
# build_cidata_iso.sh — Build cidata autoinstall ISO; optional upload to Proxmox.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HTTP="${MSSP_HTTP_DIR:-${ROOT}/http}"
OUT="${MSSP_CIDATA_OUT:-${ROOT}/.cache/mssp-appliance-cidata.iso}"
PVE_HOST="${KEVANTIC_PVE_HOST:-192.168.0.191}"
PVE_KEY="${KEVANTIC_PVE_SSH_KEY:-$HOME/.ssh/id_ed25519_proxmox}"
PVE_ISO_NAME="${MSSP_CIDATA_ISO_NAME:-mssp-appliance-cidata.iso}"
UPLOAD="${MSSP_CIDATA_UPLOAD:-1}"

[[ -f "${HTTP}/user-data" && -f "${HTTP}/meta-data" ]] || {
  echo "missing ${HTTP}/user-data or meta-data" >&2
  exit 2
}

command -v genisoimage >/dev/null || command -v xorriso >/dev/null || {
  echo "install genisoimage or xorriso" >&2
  exit 2
}

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"
if command -v xorriso >/dev/null; then
  xorriso -as mkisofs -o "$OUT" -V cidata -r -J "${HTTP}/meta-data" "${HTTP}/user-data"
else
  genisoimage -output "$OUT" -V cidata -r -J "${HTTP}/meta-data" "${HTTP}/user-data"
fi
ls -lh "$OUT"

if [[ "$UPLOAD" != "1" ]]; then
  echo CIDATA_ISO_BUILT
  exit 0
fi

[[ -f "$PVE_KEY" ]] || { echo "missing Proxmox key: $PVE_KEY" >&2; exit 2; }
scp -o BatchMode=yes -i "$PVE_KEY" "$OUT" "root@${PVE_HOST}:/var/lib/vz/template/iso/${PVE_ISO_NAME}"
ssh -i "$PVE_KEY" -o BatchMode=yes "root@${PVE_HOST}" "ls -lh /var/lib/vz/template/iso/${PVE_ISO_NAME}"
echo CIDATA_ISO_OK
