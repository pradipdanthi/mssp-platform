#!/usr/bin/env bash
# Sync Windows EDR AR pack: deploy/ is source of truth → endpoint_configs (agent ZIP).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/deploy/wazuh-active-response/windows"
DST="$ROOT/backend-api/app/endpoint_configs/windows-edr-ar"
LINUX_SRC="$ROOT/deploy/wazuh-active-response"
LINUX_DST="$ROOT/backend-api/app/endpoint_configs/linux-edr-ar"
mkdir -p "$DST" "$LINUX_DST"
for f in \
  Install-MsspWindowsEdrAr.ps1 \
  Test-MsspQuarantineProof.ps1 \
  mssp-isolate-host.cmd mssp-isolate-host.ps1 \
  mssp-kill-process.cmd mssp-kill-process.ps1 \
  mssp-block-hash.cmd mssp-block-hash.ps1 \
  Sync-MsspEdrAr.ps1 Watch-MsspQuarantine.ps1 \
  mssp-ar.env.defaults agent.conf.mssp-edr-sync.xml
do
  if [[ -f "$SRC/$f" ]]; then
    cp -a "$SRC/$f" "$DST/$f"
  fi
done
for f in mssp-isolate-host mssp-kill-process mssp-block-hash Sync-MsspEdrAr.sh; do
  if [[ -f "$LINUX_SRC/$f" ]]; then
    cp -a "$LINUX_SRC/$f" "$LINUX_DST/$f"
  fi
done
if [[ -f "$SRC/mssp-ar.env.defaults" ]]; then
  cp -a "$SRC/mssp-ar.env.defaults" "$LINUX_DST/mssp-ar.env.defaults"
fi
chmod +x "$LINUX_DST"/mssp-* "$LINUX_DST/Sync-MsspEdrAr.sh" 2>/dev/null || true
echo "PASS: synced Windows+Linux AR pack deploy/ → endpoint_configs/"
