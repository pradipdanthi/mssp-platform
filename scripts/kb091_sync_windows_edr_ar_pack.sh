#!/usr/bin/env bash
# Sync Windows EDR AR pack: deploy/ is source of truth → endpoint_configs (agent ZIP).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/deploy/wazuh-active-response/windows"
DST="$ROOT/backend-api/app/endpoint_configs/windows-edr-ar"
mkdir -p "$DST"
for f in \
  Install-MsspWindowsEdrAr.ps1 \
  Test-MsspQuarantineProof.ps1 \
  mssp-isolate-host.cmd mssp-isolate-host.ps1 \
  mssp-kill-process.cmd mssp-kill-process.ps1 \
  mssp-block-hash.cmd mssp-block-hash.ps1 \
  Sync-MsspEdrAr.ps1
do
  if [[ -f "$SRC/$f" ]]; then
    cp -a "$SRC/$f" "$DST/$f"
  fi
done
echo "PASS: synced Windows AR pack deploy/ → endpoint_configs/"
