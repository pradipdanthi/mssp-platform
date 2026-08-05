#!/usr/bin/env bash
# Track-3 — junexis-engine-api job queue + catalogue executors
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/junexis-appliance"
FAIL=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; FAIL=1; }

echo "=== Appliance Track-3 engine-api validation ==="

need() { [[ -f "$1" ]] && pass "file ${1#"$ROOT"/}" || fail "missing ${1#"$ROOT"/}"; }

need "$APP/appliance/jobs/queue.py"
need "$APP/appliance/jobs/executor.py"
need "$APP/appliance/api/local_app.py"
need "$APP/engines/junexis_engine_worker.py"

grep -q 'junexis-engine-api' "$APP/appliance/api/local_app.py" && pass "local_app identifies as junexis-engine-api" || fail "service name"
grep -q '/appliance/v1/jobs/claim' "$APP/appliance/api/local_app.py" && pass "job claim endpoint" || fail "claim missing"
grep -q '_exec_containment' "$APP/appliance/jobs/executor.py" && pass "containment executor" || fail "containment"
grep -q '_exec_easm' "$APP/appliance/jobs/executor.py" && pass "easm executor" || fail "easm"
grep -q 'process_one_job' "$APP/engines/junexis_engine_worker.py" && pass "worker claims jobs" || fail "worker jobs"

export PYTHONPATH="$APP${PYTHONPATH:+:$PYTHONPATH}"
export JUNEXIS_STATE_DIR="$(mktemp -d)"
export JUNEXIS_LOG_DIR="$(mktemp -d)"
trap 'rm -rf "$JUNEXIS_STATE_DIR" "$JUNEXIS_LOG_DIR"' EXIT

python3 - <<'PY' || fail "job queue/executor smoke"
from appliance.jobs import queue
from appliance.jobs.executor import execute_job

q = queue.enqueue(svc="svc-02", job_type="collect_evidence", payload={"agent_id": "001"})
assert q["status"] == "pending"
job = queue.claim_next("svc-02", worker_id="test")
assert job and job["job_id"] == q["job_id"]
ok, result = execute_job("svc-02", "collect_evidence", {"agent_id": "001"})
assert ok and "staged_dir" in result
queue.complete(job["job_id"], success=True, result=result)
got = queue.get_job(job["job_id"])
assert got["status"] == "success"
ok2, r2 = execute_job("svc-10", "identity_sync", {"connector": "entra", "config": {"tenant": "x"}})
assert ok2 and r2.get("status") == "configured"
print("JOB_SMOKE_OK")
PY
[[ $? -eq 0 ]] && pass "job queue/executor smoke" || true

# Compile local_app with new imports
python3 -m py_compile "$APP/appliance/api/local_app.py" \
  "$APP/appliance/jobs/queue.py" \
  "$APP/appliance/jobs/executor.py" \
  "$APP/engines/junexis_engine_worker.py" \
  && pass "python compile track-3 modules" || fail "compile"

"$ROOT/scripts/kb093e_validate_appliance_engine.sh" >/tmp/kb093e-track3.txt
tail -1 /tmp/kb093e-track3.txt | grep -q PASSED && pass "kb093e still passes" || fail "kb093e"

if [[ "$FAIL" -ne 0 ]]; then
  echo "APPLIANCE_TRACK3_ENGINE_API_VALIDATE_FAILED"
  exit 1
fi
echo "APPLIANCE_TRACK3_ENGINE_API_VALIDATE_OK"
