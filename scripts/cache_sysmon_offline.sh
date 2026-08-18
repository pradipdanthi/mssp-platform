#!/usr/bin/env bash
# Download Microsoft Sysinternals Sysmon and cache Sysmon64.exe for offline
# Windows agent ZIP builds. The binary is gitignored — never commit it.
#
# Places copies at:
#   /opt/mssp-control/.cache/sysmon/Sysmon64.exe
#   /opt/mssp-control/backend-api/app/endpoint_configs/Sysmon64.exe
#   /var/lib/mssp/sysmon-cache/Sysmon64.exe   (if writable)
#
# After this script: rebuild backend-api so Docker COPY embeds the file:
#   ./scripts/production_deploy_control_plane.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="https://download.sysinternals.com/files/Sysmon.zip"
CACHE="$ROOT/.cache/sysmon"
APP_DIR="$ROOT/backend-api/app/endpoint_configs"
HOST_CACHE="/var/lib/mssp/sysmon-cache"

log() { printf '[cache-sysmon] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

command -v curl >/dev/null 2>&1 || die "curl is required"
command -v unzip >/dev/null 2>&1 || die "unzip is required"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

log "Downloading Sysmon.zip from Microsoft Sysinternals"
curl -fsSL --retry 3 --retry-delay 2 -A "MSSP-sysmon-cache" -o "$TMP/Sysmon.zip" "$URL"
unzip -qo "$TMP/Sysmon.zip" -d "$TMP/out"

BIN=""
for name in Sysmon64.exe Sysmon.exe; do
  if [[ -f "$TMP/out/$name" ]]; then
    BIN="$TMP/out/$name"
    break
  fi
  found="$(find "$TMP/out" -iname "$name" -type f | head -1 || true)"
  if [[ -n "$found" ]]; then
    BIN="$found"
    break
  fi
done
[[ -n "$BIN" ]] || die "Sysmon64.exe not found inside Sysmon.zip"
[[ "$(stat -c%s "$BIN")" -gt 10000 ]] || die "downloaded Sysmon binary looks too small"

install_bin() {
  local dest_dir="$1"
  mkdir -p "$dest_dir"
  install -m 0644 "$BIN" "$dest_dir/Sysmon64.exe"
  log "cached $dest_dir/Sysmon64.exe ($(stat -c%s "$dest_dir/Sysmon64.exe") bytes)"
}

install_bin "$CACHE"
install_bin "$APP_DIR"
if mkdir -p "$HOST_CACHE" 2>/dev/null; then
  install_bin "$HOST_CACHE" || log "WARN: could not write $HOST_CACHE"
else
  log "WARN: $HOST_CACHE not writable (skipped)"
fi

# Companion license notice from the zip when present (also gitignored via *.exe dir).
if [[ -f "$TMP/out/Eula.txt" ]]; then
  install -m 0644 "$TMP/out/Eula.txt" "$CACHE/Eula.txt"
fi

log "OK — Sysmon64.exe is in the package-builder cache"
log "Next: rebuild backend-api so new Windows ZIPs embed windows/Sysmon64.exe"
echo SYSMON_CACHE_OK
