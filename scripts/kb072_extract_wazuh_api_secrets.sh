#!/usr/bin/env bash
# KB-072 helper: copy Wazuh API user/password from VM 101 install archive
# into control-plane secret files (never echoes secrets).
#
# Run as root ON wazuh-stack (192.168.0.211), then scp the two files to VM 100:
#   /opt/mssp-control/.secrets/wazuh_api_user
#   /opt/mssp-control/.secrets/wazuh_api_password
#
# Or run from VM 100 if you have root SSH to 211 and adjust REMOTE_*.
set -euo pipefail

TAR="${WAZUH_INSTALL_TAR:-/root/wazuh-install/wazuh-install-files.tar}"
OUT_DIR="${1:-/tmp/wazuh-api-secrets}"
mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"

if [[ ! -f "$TAR" ]]; then
  echo "Missing $TAR — run on VM 101 as root after Wazuh install." >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
tar -xf "$TAR" -C "$TMP"

# Official assistant packs passwords under wazuh-install-files/
PASS_FILE="$(find "$TMP" -name 'wazuh-passwords.txt' | head -1 || true)"
if [[ -z "$PASS_FILE" ]]; then
  echo "wazuh-passwords.txt not found inside archive." >&2
  exit 1
fi

# Extract wazuh-wui (API/dashboard) password without printing it
python3 - "$PASS_FILE" "$OUT_DIR" <<'PY'
import re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
out = Path(sys.argv[2])
user = "wazuh-wui"
# Common pattern in Wazuh password files
m = re.search(r"(?i)User:\s*wazuh-wui\s*\n\s*Password:\s*(\S+)", text)
if not m:
    m = re.search(r"(?i)wazuh-wui.*?password[:\s]+(\S+)", text, re.S)
if not m:
    raise SystemExit("Could not parse wazuh-wui password from passwords file")
(out / "wazuh_api_user").write_text(user + "\n")
(out / "wazuh_api_password").write_text(m.group(1) + "\n")
(out / "wazuh_api_user").chmod(0o600)
(out / "wazuh_api_password").chmod(0o600)
print("Wrote wazuh_api_user and wazuh_api_password (contents not shown).")
PY

echo "Copy these to mssp-control VM 100:"
echo "  scp $OUT_DIR/wazuh_api_user $OUT_DIR/wazuh_api_password secadmin@192.168.0.201:/opt/mssp-control/.secrets/"
echo "Then: cd /opt/mssp-control && docker compose up -d backend-api"
echo "Then Admin → Customers → Provision all engines"
