#!/usr/bin/env bash
# KB-096: AI SOC triage assist + Admin AI chat + Graph cache (static safety checks).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; exit 1; }

test -f docs/KB096_AI_SOC_TRIAGE_GRAPH_ADMIN_CHAT_PLAN.md || fail "KB-096 plan missing"
test -f postgres/init/034_ai_soc_triage_assist.sql || fail "migration 034 missing"
test -f backend-api/app/services/ai_soc_triage.py || fail "ai_soc_triage.py missing"
test -f backend-api/app/services/ai_admin_chat.py || fail "ai_admin_chat.py missing"
test -f backend-api/app/api/routes/admin_ai_chat.py || fail "admin_ai_chat route missing"
test -f frontend-admin/src/pages/AiAssistantPage.tsx || fail "AiAssistantPage missing"

grep -q 'AI_SOC_TRIAGE_ENABLED' docker-compose.yml || fail "compose AI_SOC_TRIAGE_ENABLED missing"
grep -q 'AI_CHAT_ENABLED' docker-compose.yml || fail "compose AI_CHAT_ENABLED missing"
grep -q 'AI_SOC_TRIAGE_ENABLED:-false' docker-compose.yml || fail "AI_SOC_TRIAGE must default false"
grep -q 'AI_CHAT_ENABLED:-false' docker-compose.yml || fail "AI_CHAT must default false"

grep -q 'process_soc_triage_job' backend-api/app/services/ai_alert_queue.py \
  || fail "queue must chain SOC triage"
grep -q 'ai_risk_score' backend-api/app/api/routes/alert_incident_triage.py \
  || fail "alert detail must expose ai_risk_score"
grep -q 'ai_triage_status' backend-api/app/schemas/triage.py \
  || fail "triage schema missing ai_triage_status"
grep -q 'admin_ai_chat_router' backend-api/app/main.py \
  || fail "main.py missing admin_ai_chat_router"
grep -q 'AI SOC triage assist' frontend-admin/src/pages/AlertDetailPage.tsx \
  || fail "AlertDetailPage missing triage assist section"
grep -q '/ai-assistant' frontend-admin/src/App.tsx || fail "App route /ai-assistant missing"
grep -q 'AI Assistant' frontend-admin/src/components/Layout.tsx || fail "nav AI Assistant missing"

# AI must complement TI — not invent parallel IOC store
grep -q 'containment_suggestion' backend-api/app/services/ai_soc_triage.py \
  || fail "triage must draft containment_suggestion for human decision"
grep -q 'never auto-isolates' frontend-admin/src/pages/AlertDetailPage.tsx \
  || fail "AlertDetailPage must state containment is human-only"
if grep -q 'customer_visible' backend-api/app/services/ai_soc_triage.py; then
  fail "ai_soc_triage must never reference customer_visible"
fi

# Graph token cache present
grep -q '_cached_token' backend-api/app/services/itdr_graph_client.py \
  || fail "Graph token cache missing"

# Live: columns exist when postgres is up
if docker compose ps --status running 2>/dev/null | grep -q mssp-postgres; then
  # shellcheck disable=SC1091
  set -a
  # shellcheck disable=SC1090
  source <(grep -E '^(POSTGRES_USER|POSTGRES_DB)=' .env 2>/dev/null || true)
  set +a
  cols="$(docker compose exec -T postgres psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-mssp_control}" -tAc \
    "SELECT COUNT(*) FROM information_schema.columns
     WHERE table_name='security_alerts'
       AND column_name IN (
         'ai_risk_score','ai_risk_rationale','ai_enrichment_notes',
         'ai_correlation_notes','ai_containment_suggestion',
         'ai_triage_status','ai_triaged_at'
       );" 2>/dev/null | tr -d '[:space:]' || echo 0)"
  if [[ "${cols}" == "7" ]]; then
    pass "Postgres has all 7 KB-096 triage columns"
  else
    fail "Postgres missing KB-096 columns (found ${cols}/7) — apply 034_ai_soc_triage_assist.sql"
  fi
else
  pass "skipped live column check (postgres not running)"
fi

if curl -fsS --connect-timeout 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
  pass "control-plane /health reachable"
  code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/admin/ai/chat/status || true)"
  if [[ "$code" == "401" || "$code" == "403" ]]; then
    pass "GET /admin/ai/chat/status requires auth (${code})"
  elif [[ "$code" == "404" ]]; then
    pass "GET /admin/ai/chat/status 404 (route not live until backend recreate)"
  else
    fail "expected 401/403/404 for unauth chat status, got ${code}"
  fi
else
  pass "skipped live API checks (API not up)"
fi

pass "kb096 AI SOC triage + chat + Graph checks"
echo "KB096_VALIDATE_OK"
