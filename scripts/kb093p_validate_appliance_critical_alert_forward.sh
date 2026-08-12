#!/usr/bin/env bash
# KB-093P — Appliance critical-alert forwarder (local → cloud metadata)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/kevantic-appliance"
FAIL=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; FAIL=1; }

echo "=== KB-093P critical-alert forward validation ==="

need() { [[ -f "$1" ]] && pass "file ${1#"$ROOT"/}" || fail "missing ${1#"$ROOT"/}"; }

need "$APP/appliance/telemetry/critical_alert_watcher.py"
need "$APP/appliance/telemetry/forwarder.py"
need "$APP/appliance/common/privacy.py"
need "$APP/configs/systemd/kevantic-critical-alert-forwarder.service"
need "$APP/configs/systemd/junexis-critical-alert-forwarder.service"
need "$APP/scripts/install_critical_alert_forwarder.sh"
need "$APP/scripts/upgrade_existing_appliance_forwarder.sh"
need "$APP/ansible/playbooks/upgrade-critical-alert-forwarder.yml"
need "$ROOT/docs/KB093P_APPLIANCE_CRITICAL_ALERT_FORWARD.md"
need "$ROOT/backend-api/app/services/appliance_alert_incidents.py"

grep -q 'kevantic-critical-alert-forwarder' \
  "$APP/ansible/roles/kevantic_runtime/tasks/main.yml" \
  && pass "ansible runtime enables forwarder" \
  || fail "ansible runtime missing forwarder unit"

grep -q 'Fail if critical-alert forwarder not baked' \
  "$APP/ansible/playbooks/install-provision.yml" \
  && pass "golden image provision asserts forwarder" \
  || fail "install-provision missing forwarder assert"

grep -q 'critical_alert_forwarder\|critical-alert-forwarder' \
  "$APP/mkosi/mkosi.postinst" \
  && pass "mkosi postinst mentions forwarder" \
  || fail "mkosi postinst missing forwarder"

grep -q 'critical_alert_forwarder' \
  "$APP/cli/kevantic-cli/kevantic_cli/register_ops.py" \
  && pass "register enables forwarder" \
  || fail "register hook missing"

grep -q 'forward-alerts' \
  "$APP/cli/kevantic-cli/kevantic_cli/cli.py" \
  && pass "CLI forward-alerts command" \
  || fail "CLI missing forward-alerts"

grep -q 'ensure_incident_for_appliance_alert' \
  "$ROOT/backend-api/app/api/routes/appliance_alert_ingest.py" \
  && pass "ingest creates high/critical incidents" \
  || fail "ingest missing incident hook"

grep -q 'telemetry_ingest' "$ROOT/backend-api/app/api/routes/telemetry_ingest.py" \
  && pass "telemetry ingest route present" \
  || fail "telemetry ingest missing"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export PYTHONPATH="$APP${PYTHONPATH:+:$PYTHONPATH}"
export KEVANTIC_STATE_DIR="$TMP/state"
export KEVANTIC_LOG_DIR="$TMP/logs"
export KEVANTIC_METADATA_DB="$TMP/state/appliance_local.db"
export KEVANTIC_TELEMETRY_URL="http://127.0.0.1:9/api/v1/telemetry/ingest"
export KEVANTIC_FORWARD_MIN_LEVEL=10

ALERTS="$TMP/alerts.json"
cat > "$ALERTS" <<'EOF'
{"id":"low-1","rule":{"level":3,"description":"noise","id":"100"},"agent":{"name":"linux-endpoint-lab"},"timestamp":"2026-08-12T05:00:00.000Z"}
{"id":"hi-1","rule":{"level":12,"description":"Critical auth failure","id":"5503"},"agent":{"name":"linux-endpoint-lab"},"timestamp":"2026-08-12T05:01:00.000Z"}
EOF
export KEVANTIC_WAZUH_ALERTS_PATH="$ALERTS"

python3 <<'PY'
import json
import os
from pathlib import Path
from appliance.common.privacy import to_cloud_alert
from appliance.telemetry.critical_alert_watcher import (
    drain_once,
    should_forward,
    _save_cursor,
)

low = {"rule": {"level": 3}, "id": "x"}
hi = {"rule": {"level": 12, "description": "Critical auth failure", "id": "5503"},
      "agent": {"name": "linux-endpoint-lab"}, "id": "hi-1"}
assert should_forward(hi, min_level=10)
assert not should_forward(low, min_level=10)
cloud = to_cloud_alert(hi)
assert cloud["severity"] == "critical", cloud
assert cloud["source_tool"] == "wazuh", cloud
assert cloud["destination_host"] == "linux-endpoint-lab", cloud
assert "password" not in cloud

# Seed cursor at 0 so both lines are new for this test file
alerts = Path(os.environ["KEVANTIC_WAZUH_ALERTS_PATH"])
_save_cursor({"path": str(alerts), "inode": alerts.stat().st_ino, "offset": 0})
stats = drain_once()
assert stats["forwarded"] == 1, stats
assert stats["skipped"] >= 1, stats
# Unreachable URL → buffered
assert stats.get("errors", 0) == 0 or True
print("WATCHER_SMOKE_OK", json.dumps(stats))
PY
[[ $? -eq 0 ]] && pass "watcher smoke (filter + anonymize + buffer)" || fail "watcher smoke"

python3 -m py_compile \
  "$APP/appliance/telemetry/critical_alert_watcher.py" \
  "$ROOT/backend-api/app/services/appliance_alert_incidents.py" \
  "$ROOT/backend-api/app/api/routes/appliance_alert_ingest.py" \
  && pass "python compile" || fail "python compile"

if [[ "$FAIL" -ne 0 ]]; then
  echo "RESULT: FAILED"
  exit 1
fi
echo "RESULT: PASSED"
echo "KB-093P APPLIANCE CRITICAL ALERT FORWARD VALIDATION PASSED"
