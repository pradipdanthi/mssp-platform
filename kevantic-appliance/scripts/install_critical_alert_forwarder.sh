#!/usr/bin/env bash
# Install / refresh the local→cloud critical-alert forwarder on an appliance.
# Safe to re-run. Intended for on_prem_appliance / cloud_appliance / hybrid.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${KEVANTIC_APPLIANCE_SRC:-/opt/kevantic/appliance-src}"
UNIT_DST=/etc/systemd/system/kevantic-critical-alert-forwarder.service

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root (or with sudo)." >&2
  exit 1
fi

mkdir -p "$SRC/appliance/telemetry" "$SRC/appliance/common" \
  /var/lib/kevantic /var/log/kevantic /etc/kevantic /run/kevantic

# Sync appliance Python package pieces needed by the forwarder
rsync -a --delete \
  "$REPO_ROOT/appliance/" "$SRC/appliance/"

install -m 0644 \
  "$REPO_ROOT/configs/systemd/kevantic-critical-alert-forwarder.service" \
  "$UNIT_DST"

# Ensure telemetry URL points at this control plane when registered
if [[ -f /var/lib/kevantic/appliance.json ]]; then
  CP="$(python3 - <<'PY'
import json
from pathlib import Path
p=Path("/var/lib/kevantic/appliance.json")
print((json.loads(p.read_text()).get("control_plane") or "").rstrip("/"))
PY
)"
  if [[ -n "$CP" ]]; then
    ENV_FILE=/etc/kevantic/appliance.env
    touch "$ENV_FILE"
    chmod 0640 "$ENV_FILE"
    grep -q '^KEVANTIC_TELEMETRY_URL=' "$ENV_FILE" 2>/dev/null \
      && sed -i "s|^KEVANTIC_TELEMETRY_URL=.*|KEVANTIC_TELEMETRY_URL=${CP}/api/v1/telemetry/ingest|" "$ENV_FILE" \
      || echo "KEVANTIC_TELEMETRY_URL=${CP}/api/v1/telemetry/ingest" >> "$ENV_FILE"
    # Appliance id for headers (key remains in secrets file)
    AID="$(python3 - <<'PY'
import json
from pathlib import Path
print(json.loads(Path("/var/lib/kevantic/appliance.json").read_text()).get("appliance_id") or "")
PY
)"
    if [[ -n "$AID" ]]; then
      grep -q '^KEVANTIC_APPLIANCE_ID=' "$ENV_FILE" 2>/dev/null \
        && sed -i "s|^KEVANTIC_APPLIANCE_ID=.*|KEVANTIC_APPLIANCE_ID=${AID}|" "$ENV_FILE" \
        || echo "KEVANTIC_APPLIANCE_ID=${AID}" >> "$ENV_FILE"
    fi
  fi
fi

systemctl daemon-reload
systemctl enable --now kevantic-critical-alert-forwarder.service
systemctl --no-pager --full status kevantic-critical-alert-forwarder.service | head -20
echo "OK: critical-alert forwarder installed and started"
