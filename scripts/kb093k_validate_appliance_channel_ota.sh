#!/usr/bin/env bash
# Track-4 — channeld + OTA staging + control-plane channel gateway
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/junexis-appliance"
FAIL=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; FAIL=1; }

echo "=== Appliance Track-4 channel/OTA validation ==="

need() { [[ -f "$1" ]] && pass "file ${1#"$ROOT"/}" || fail "missing ${1#"$ROOT"/}"; }

need "$APP/channel/channeld/__main__.py"
need "$APP/ota/junexis_ota.py"
need "$APP/configs/systemd/junexis-channeld.service"
need "$ROOT/postgres/init/031_appliance_channel_ota.sql"
need "$ROOT/backend-api/app/api/routes/appliance_channel.py"
need "$ROOT/backend-api/app/services/appliance_channel.py"

for role in channel_agent ota_staging; do
  if grep -q 'scaffold-only' "$APP/ansible/roles/$role/tasks/main.yml"; then
    fail "role $role still scaffold-only"
  else
    pass "role $role implemented"
  fi
done

grep -q 'junexis-channeld' "$APP/ansible/roles/channel_agent/tasks/main.yml" && pass "channel_agent installs channeld" || fail "channeld install"
grep -q 'junexis-ota' "$APP/ansible/roles/ota_staging/tasks/main.yml" && pass "ota_staging installs junexis-ota" || fail "ota install"
grep -q 'appliance_channel_router' "$ROOT/backend-api/app/main.py" && pass "main.py wires channel router" || fail "main wire"
grep -q 'cmd_channel' "$APP/cli/junexis-cli/junexis_cli/cli.py" && pass "CLI channel command" || fail "CLI channel"

# OTA smoke
export PYTHONPATH="$APP/ota:$APP/cli/junexis-cli${PYTHONPATH:+:$PYTHONPATH}"
export JUNEXIS_STATE_DIR="$(mktemp -d)"
export JUNEXIS_OTA_DIR="$JUNEXIS_STATE_DIR/ota"
export JUNEXIS_OTA_ALLOW_UNSIGNED=1
trap 'rm -rf "$JUNEXIS_STATE_DIR"' EXIT
python3 - <<'PY' || fail "ota smoke"
from junexis_ota import apply_offer, status
r = apply_offer({"version": "0.1.0-test", "component": "junexis-appliance-meta", "notes": "t", "auto_apply": True})
assert r.get("ok"), r
s = status()
assert s["current"]["version"] == "0.1.0-test"
print("OTA_SMOKE_OK")
PY
pass "ota stage/apply smoke"

# channeld module imports
PYTHONPATH="$APP/channel:$APP/cli/junexis-cli:$APP/ota${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -c "import channeld; print('channeld_ok')" | grep -q channeld_ok && pass "channeld import" || fail "channeld import"

# Live DB + API when stack is up
if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
  pass "/health OK"
  OA="$(curl -fsS http://localhost:8000/openapi.json)"
  echo "$OA" | grep -q '/appliance/channel/poll' && pass "OpenAPI channel poll" || fail "OpenAPI poll"
  echo "$OA" | grep -q '/appliance/channel/frames' && pass "OpenAPI channel frames" || fail "OpenAPI frames"
  grep -q 'websocket' "$ROOT/backend-api/app/api/routes/appliance_channel.py" \
    && pass "websocket channel route in source" || fail "websocket route missing"
  if docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
    psql -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" -c '\d appliance_channel_inbox' >/tmp/ch_inbox.txt 2>/dev/null; then
    grep -q frame_type /tmp/ch_inbox.txt && pass "DB appliance_channel_inbox" || fail "inbox schema"
  else
    fail "appliance_channel_inbox missing (apply 031 migration)"
  fi
else
  echo "WARN: backend not up — skipped live OpenAPI/DB checks"
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "APPLIANCE_TRACK4_CHANNEL_OTA_VALIDATE_FAILED"
  exit 1
fi
echo "APPLIANCE_TRACK4_CHANNEL_OTA_VALIDATE_OK"
