#!/usr/bin/env bash
# Push latest MSSP EDR active-response scripts to an appliance local Wazuh Manager.
# Installs Linux bin scripts, Windows edr-ar pack, publishes to /var/ossec/etc/shared/*,
# and re-registers AR commands (timeout_allowed=no, 1m Sync-MsspEdrAr wodle).
#
# Usage:
#   ./kevantic-appliance/scripts/sync_appliance_edr_ar_scripts.sh <appliance-ip> [ssh-user] [ssh-key]
#
# Examples:
#   ./kevantic-appliance/scripts/sync_appliance_edr_ar_scripts.sh 192.168.0.226 junexis
#   ./kevantic-appliance/scripts/sync_appliance_edr_ar_scripts.sh 192.168.0.225 packer
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CTRL="$(cd "$ROOT/.." && pwd)"
HOST="${1:-}"
USER_NAME="${2:-junexis}"
SSH_KEY="${3:-${ROOT}/.tools/build-ssh/kevantic_packer}"
EDR_AR_VERSION="${MSSP_EDR_AR_VERSION:-1.0.1}"

usage() {
  echo "Usage: $0 <appliance-ip> [ssh-user] [ssh-key]" >&2
  exit 1
}

[[ -n "$HOST" ]] || usage
[[ -f "$SSH_KEY" ]] || { echo "Missing SSH key: $SSH_KEY" >&2; exit 1; }

AR_SRC="$CTRL/deploy/wazuh-active-response"
WIN_AR="$AR_SRC/windows"
[[ -x "$AR_SRC/mssp-isolate-host" ]] || { echo "Missing Linux AR: $AR_SRC/mssp-isolate-host" >&2; exit 1; }
[[ -f "$WIN_AR/mssp-isolate-host.ps1" ]] || { echo "Missing Windows AR: $WIN_AR/mssp-isolate-host.ps1" >&2; exit 1; }
[[ -f "$WIN_AR/Watch-MsspQuarantine.ps1" ]] || { echo "Missing watchdog: $WIN_AR/Watch-MsspQuarantine.ps1" >&2; exit 1; }

SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${USER_NAME}@${HOST}")
SCP=(scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
GIT_COMMIT="$(git -C "$CTRL" rev-parse --short HEAD 2>/dev/null || echo unknown)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> Sync EDR AR v${EDR_AR_VERSION} (git ${GIT_COMMIT}) → ${USER_NAME}@${HOST}"

cp "$AR_SRC/mssp-isolate-host" "$AR_SRC/mssp-kill-process" "$AR_SRC/mssp-block-hash" "$TMP/"
for f in \
  mssp-isolate-host.ps1 mssp-isolate-host.cmd \
  mssp-kill-process.ps1 mssp-kill-process.cmd \
  mssp-block-hash.ps1 mssp-block-hash.cmd \
  Sync-MsspEdrAr.ps1 Watch-MsspQuarantine.ps1
do
  cp "$WIN_AR/$f" "$TMP/$f"
done

"${SCP[@]}" "$TMP"/* "${USER_NAME}@${HOST}:/tmp/"

"${SSH[@]}" "sudo bash -s" <<REMOTE
set -euo pipefail
EDR_AR_VERSION="${EDR_AR_VERSION}"
GIT_COMMIT="${GIT_COMMIT}"

for f in mssp-isolate-host mssp-kill-process mssp-block-hash; do
  install -o root -g wazuh -m 0750 "/tmp/\$f" "/var/ossec/active-response/bin/\$f"
done

install -d -m 0755 /var/lib/junexis/edr-ar/windows /var/lib/kevantic/edr-ar/windows
for f in mssp-isolate-host.ps1 mssp-isolate-host.cmd mssp-kill-process.ps1 mssp-kill-process.cmd mssp-block-hash.ps1 mssp-block-hash.cmd Sync-MsspEdrAr.ps1 Watch-MsspQuarantine.ps1; do
  install -o wazuh -g wazuh -m 0640 "/tmp/\$f" "/var/lib/junexis/edr-ar/windows/\$f"
  install -o wazuh -g wazuh -m 0640 "/tmp/\$f" "/var/lib/kevantic/edr-ar/windows/\$f"
done

if [[ -d /opt/junexis/cli/junexis_cli ]]; then
  env PYTHONPATH=/opt/junexis/cli:/opt/junexis python3 -c 'from junexis_cli.register_ops import _ensure_local_edr_ar_commands; _ensure_local_edr_ar_commands()'
elif [[ -d /opt/kevantic/cli/kevantic_cli ]]; then
  env PYTHONPATH=/opt/kevantic/cli:/opt/kevantic python3 -c 'from kevantic_cli.register_ops import _ensure_local_edr_ar_commands; _ensure_local_edr_ar_commands()'
else
  echo "WARN: CLI missing — scripts installed but shared publish skipped" >&2
fi

for path in /etc/junexis/image-release.json /etc/kevantic/image-release.json; do
  if [[ -f "\$path" ]]; then
    python3 - <<PY
import json
from pathlib import Path
p = Path("\$path")
data = json.loads(p.read_text(encoding="utf-8"))
data["edr_ar_version"] = "\${EDR_AR_VERSION}"
data["git_commit"] = "\${GIT_COMMIT}"
p.write_text(json.dumps(data, indent=2) + "\\n", encoding="utf-8")
PY
  fi
done

echo "== verify permissions =="
stat -c '%U:%G %a %n' /var/ossec/active-response/bin/mssp-isolate-host
stat -c '%U:%G %a %n' /var/lib/junexis/edr-ar/windows/mssp-isolate-host.ps1 2>/dev/null || \
  stat -c '%U:%G %a %n' /var/lib/kevantic/edr-ar/windows/mssp-isolate-host.ps1

SHARED=\$(ls -d /var/ossec/etc/shared/*/mssp-isolate-host.ps1 2>/dev/null | head -1)
[[ -n "\$SHARED" ]] || { echo "FAIL: no shared mssp-isolate-host.ps1" >&2; exit 2; }
grep -q 'Invoke-MsspUnisolate' "\$SHARED" || { echo "FAIL: shared script stale (no Invoke-MsspUnisolate)" >&2; exit 2; }
grep -q 'Repair-MsspDnsConnectivity' "\$SHARED" || { echo "FAIL: shared script missing DNS restore" >&2; exit 2; }
grep -q 'mssp-edr-ar-sync' /var/ossec/etc/shared/*/agent.conf 2>/dev/null || { echo "FAIL: mssp-edr-ar-sync wodle missing" >&2; exit 2; }
grep -q '<name>mssp-isolate-host.cmd</name>' /var/ossec/etc/ossec.conf

echo "APPLIANCE_EDR_AR_SYNC_OK version=\${EDR_AR_VERSION} shared=\${SHARED}"
REMOTE

echo "==> OK — EDR AR synced on ${HOST}"
