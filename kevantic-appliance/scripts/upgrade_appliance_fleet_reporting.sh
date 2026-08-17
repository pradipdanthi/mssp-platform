#!/usr/bin/env bash
# Push fleet-reporting heartbeat fixes to a live appliance (CLI + core entitlements + image metadata).
# Field upgrade for already-deployed appliances (e.g. Beta).
# Golden VM 199: use scripts/bake_golden_vm199_fleet_reporting.sh instead (no entitlement seed).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${1:-}"
USER_NAME="${2:-junexis}"
SSH_KEY="${3:-${ROOT}/.tools/build-ssh/kevantic_packer}"

usage() {
  echo "Usage: $0 <appliance-ip> [ssh-user] [ssh-key]" >&2
  echo "Example: $0 192.168.0.226 junexis" >&2
  exit 1
}

[[ -n "$HOST" ]] || usage
[[ -f "$SSH_KEY" ]] || { echo "Missing SSH key: $SSH_KEY" >&2; exit 1; }

SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${USER_NAME}@${HOST}")
SCP=(scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)

GIT_COMMIT="$(git -C "$ROOT/.." rev-parse --short HEAD 2>/dev/null || echo unknown)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

brandify() {
  local src="$1" dst="$2"
  sed \
    -e 's/kevantic_cli/junexis_cli/g' \
    -e 's/KEVANTIC_/JUNEXIS_/g' \
    -e 's/kevantic-cli/junexis-cli/g' \
    -e 's/Kevantic/Junexis/g' \
    "$src" > "$dst"
}

brandify "$ROOT/cli/kevantic-cli/kevantic_cli/register_ops.py" "$TMP/register_ops.py"
brandify "$ROOT/cli/kevantic-cli/kevantic_cli/state.py" "$TMP/state.py"

echo "==> Install updated CLI modules on ${HOST}"
"${SCP[@]}" "$TMP/register_ops.py" "${USER_NAME}@${HOST}:/tmp/register_ops.py"
"${SCP[@]}" "$TMP/state.py" "${USER_NAME}@${HOST}:/tmp/state.py"
"${SCP[@]}" "$ROOT/configs/image-release.json" "${USER_NAME}@${HOST}:/tmp/image-release.json"

"${SSH[@]}" "bash -s" <<REMOTE
set -euo pipefail
CLI="/opt/junexis/cli/junexis_cli"
if [[ ! -d "\$CLI" ]]; then
  CLI="/opt/kevantic/cli/kevantic_cli"
fi
sudo install -m 0644 /tmp/register_ops.py "\$CLI/register_ops.py"
sudo install -m 0644 /tmp/state.py "\$CLI/state.py"
sudo install -d /etc/junexis /etc/kevantic
sudo install -m 0644 /tmp/image-release.json /etc/junexis/image-release.json
sudo install -m 0644 /tmp/image-release.json /etc/kevantic/image-release.json
sudo python3 - <<'PY'
import json
from pathlib import Path
for path in (Path("/etc/junexis/image-release.json"), Path("/etc/kevantic/image-release.json")):
    data = json.loads(path.read_text())
    data["git_commit"] = "${GIT_COMMIT}"
    path.write_text(json.dumps(data, indent=2) + "\n")
PY

# Seed core entitlement when license file left engines idle (lab appliances).
sudo python3 - <<'PY'
import json
from pathlib import Path
for state_dir in (Path("/var/lib/junexis"), Path("/var/lib/kevantic")):
    path = state_dir / "entitlements.json"
    if not path.is_file():
        continue
    data = json.loads(path.read_text())
    if data.get("service_ids"):
        continue
    data.update({
        "service_ids": ["svc-01"],
        "core": True,
        "note": "Lab core entitlement seeded by upgrade_appliance_fleet_reporting.sh",
    })
    path.write_text(json.dumps(data, indent=2) + "\n")
    print("seeded", path)
PY

sudo systemctl daemon-reload
for t in junexis-heartbeat.timer kevantic-heartbeat.timer; do
  if systemctl list-unit-files "\$t" --no-legend 2>/dev/null | grep -q .; then
    sudo systemctl restart "\$t"
    sudo systemctl start "\${t%.timer}.service" || true
  fi
done
REMOTE

echo "==> Manual heartbeat (verify enabled_services + resource metrics)"
"${SSH[@]}" 'sudo systemctl start junexis-heartbeat.service 2>/dev/null || sudo systemctl start kevantic-heartbeat.service'
sleep 2

echo "==> OK — fleet reporting upgrade applied on ${HOST} (git_commit=${GIT_COMMIT})"
