#!/usr/bin/env bash
# KB-093E — DuckDB/Parquet lake + anonymizing forwarder + retrospective hunter
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/junexis-appliance"
FAIL=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; FAIL=1; }

echo "=== KB-093E appliance engine validation ==="

need() { [[ -f "$1" ]] && pass "file ${1#"$ROOT"/}" || fail "missing ${1#"$ROOT"/}"; }

need "$APP/appliance/datalake/archiver.py"
need "$APP/appliance/datalake/query_engine.py"
need "$APP/appliance/telemetry/forwarder.py"
need "$APP/appliance/hunting/retrospective_sweeper.py"
need "$APP/appliance/api/local_app.py"
need "$APP/appliance/common/privacy.py"
need "$APP/appliance/common/metadata_db.py"
need "$APP/requirements-engine.txt"
need "$ROOT/docs/KB093E_APPLIANCE_ENGINE_DATALAKE_TELEMETRY_HUNT.md"
need "$ROOT/backend-api/app/api/routes/telemetry_ingest.py"

grep -q 'telemetry_ingest_router' "$ROOT/backend-api/app/main.py" \
  && pass "main.py wires telemetry_ingest_router" \
  || fail "main.py missing telemetry_ingest_router"

grep -q '/api/v1/telemetry' "$ROOT/backend-api/app/api/routes/telemetry_ingest.py" \
  && pass "telemetry route prefix" \
  || fail "telemetry route prefix"

# Install duckdb into local target if missing (no sudo)
DEPS="$APP/.tools/pydeps"
mkdir -p "$DEPS"
export PYTHONPATH="$APP:$DEPS${PYTHONPATH:+:$PYTHONPATH}"
if ! python3 -c "import duckdb" 2>/dev/null; then
  echo "--- installing duckdb into $DEPS ---"
  python3 -m pip install --target "$DEPS" -q -r "$APP/requirements-engine.txt" \
    || fail "duckdb install failed"
fi
python3 -c "import duckdb; print('duckdb', duckdb.__version__)" && pass "duckdb import" || fail "duckdb import"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export JUNEXIS_STATE_DIR="$TMP/state"
export JUNEXIS_LOG_DIR="$TMP/logs"
export JUNEXIS_DATALAKE_DIR="$TMP/logs/datalake"
export JUNEXIS_METADATA_DB="$TMP/state/appliance_local.db"
export JUNEXIS_TELEMETRY_URL="http://127.0.0.1:9/api/v1/telemetry/ingest"  # closed port → buffer

python3 <<'PY'
import json
from pathlib import Path
from appliance.common.privacy import scrub, to_cloud_alert
from appliance.datalake.archiver import DataLakeArchiver
from appliance.datalake.query_engine import QueryEngine
from appliance.telemetry.forwarder import TelemetryForwarder
from appliance.hunting.retrospective_sweeper import RetrospectiveSweeper

# Privacy
raw = {
  "password": "secret123",
  "alert_title": "Test",
  "source_tool": "wazuh",
  "id": "e1",
  "severity": "high",
  "source_ip": "10.0.0.5",
  "data": {"email_body": "confidential", "srcip": "10.0.0.5", "sha256": "d41d8cd98f00b204e9800998ecf8427e"},
  "timestamp": "2026-08-04T10:00:00Z",
}
clean = scrub(raw)
assert clean["password"] == "[REDACTED]", clean
cloud = to_cloud_alert(raw)
assert "password" not in cloud
assert "source_ip" not in cloud
assert cloud["severity"] == "high"

# Archive + query
arch = DataLakeArchiver()
path = arch.archive_events([
  {
    "id": "e1",
    "source_tool": "wazuh",
    "timestamp": "2026-08-04T10:00:00Z",
    "src_ip": "192.168.1.50",
    "cve": "CVE-2026-1234",
    "file_hash": "d41d8cd98f00b204e9800998ecf8427e",
    "domain_name": "evil.example",
  },
  {
    "id": "e2",
    "source_tool": "suricata",
    "timestamp": "2026-08-04T11:00:00Z",
    "dst_ip": "192.168.1.50",
  },
], source_hint="test")
assert path.exists() and path.suffix == ".parquet", path

qe = QueryEngine()
hits = qe.search(["192.168.1.50", "CVE-2026-1234"], lookback_days=30, limit=50)
assert hits, "expected hunt hits"
print("hits", len(hits))

# Forwarder buffers when unreachable
fwd = TelemetryForwarder()
res = fwd.forward_event(raw)
assert res.get("buffered") is True, res
stats = fwd.flush_buffer()
assert "sent" in stats

# Retrospective job
sw = RetrospectiveSweeper()
out = sw.run_job({
  "job_id": "job_123",
  "iocs": ["192.168.1.50", "d41d8cd98f00b204e9800998ecf8427e", "CVE-2026-1234"],
  "lookback_days": 90,
})
assert out["status"] == "completed"
assert out["hit_count"] >= 1
assert sw.get_job("job_123")["status"] == "completed"
print("ENGINE_SMOKE_OK")
PY
[[ $? -eq 0 ]] && pass "engine smoke (archive/query/forward/hunt)" || fail "engine smoke"

# Compile check local API
python3 -m py_compile "$APP/appliance/api/local_app.py" && pass "local_app compiles" || fail "local_app compile"

if [[ "$FAIL" -ne 0 ]]; then
  echo "KB-093E APPLIANCE ENGINE DATALAKE TELEMETRY HUNT VALIDATION FAILED"
  exit 1
fi
echo "KB-093E APPLIANCE ENGINE DATALAKE TELEMETRY HUNT VALIDATION PASSED"
