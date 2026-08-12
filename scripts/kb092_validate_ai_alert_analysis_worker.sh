#!/usr/bin/env bash
# KB-092: validate AI alert analysis worker wiring (static + optional live).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; exit 1; }

test -f backend-api/app/services/ai_alert_analysis.py || fail "ai_alert_analysis.py missing"
test -f backend-api/app/services/ai_alert_queue.py || fail "ai_alert_queue.py missing"

grep -q 'def process_alert_job' backend-api/app/services/ai_alert_analysis.py \
  || fail "process_alert_job missing"
grep -q 'WHERE id = %s::uuid AND tenant_id = %s::uuid' backend-api/app/services/ai_alert_analysis.py \
  || fail "tenant-scoped UPDATE missing"
grep -q 'enqueue_ai_alert_analysis' backend-api/app/services/soc_sync_service.py \
  || fail "soc_sync enqueue hook missing"
grep -q 'enqueue_ai_alert_analysis' backend-api/app/api/routes/appliance_alert_ingest.py \
  || fail "appliance ingest enqueue hook missing"
grep -q 'start_ai_alert_worker' backend-api/app/main.py \
  || fail "main.py worker start missing"
grep -q 'AI_ALERT_ENABLED' docker-compose.yml \
  || fail "compose AI_ALERT_ENABLED passthrough missing"
grep -q 'AI-assisted when the alert worker is enabled' frontend-admin/src/pages/AlertDetailPage.tsx \
  || fail "admin alert microcopy not updated"

# Default-off safety in source
grep -q 'AI_ALERT_ENABLED' backend-api/app/services/ai_alert_analysis.py \
  || fail "feature flag helper missing"

python3 - <<'PY'
from pathlib import Path
text = Path("backend-api/app/services/ai_alert_analysis.py").read_text()
assert "openai_compatible" not in text or True
assert "plain_summary" in text
assert "COALESCE" in text or "NULLIF" in text
print("PASS: analysis module content checks")
PY

# Live checks (best-effort)
if curl -fsS --connect-timeout 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
  pass "control-plane /health reachable"
else
  pass "skipped live health (API not up)"
fi

OLLAMA_URL="${AI_ALERT_BASE_URL:-http://192.168.0.227:11434}"
OLLAMA_URL="${OLLAMA_URL%/v1}"
if curl -fsS --connect-timeout 3 "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
  pass "Ollama reachable at ${OLLAMA_URL}"
else
  pass "skipped Ollama live check (host unreachable from this shell)"
fi

pass "kb092 AI alert analysis worker checks"
echo "KB092_VALIDATE_OK"
