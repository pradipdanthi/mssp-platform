#!/usr/bin/env bash
# Track-1 appliance closure: packages, inventory, jobs, register CLI, Admin fields.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; FAIL=1; }

echo "=== Appliance Track-1 closure validation ==="

need() {
  [[ -f "$1" ]] && pass "file ${1#"$ROOT"/}" || fail "missing ${1#"$ROOT"/}"
}

need "$ROOT/postgres/init/030_appliance_jobs_agent_inventory.sql"
need "$ROOT/backend-api/app/services/appliance_manager_resolver.py"
need "$ROOT/backend-api/app/services/appliance_jobs.py"
need "$ROOT/backend-api/app/services/appliance_agent_inventory.py"
need "$ROOT/kevantic-appliance/cli/kevantic-cli/kevantic_cli/register_ops.py"
need "$ROOT/kevantic-appliance/configs/systemd/kevantic-heartbeat.timer"

grep -Fq "resolve_tenant_manager_address" \
  "$ROOT/backend-api/app/api/routes/admin_agent_packages.py" \
  && pass "admin packages use appliance manager resolver" \
  || fail "admin packages missing resolver"

grep -Fq "resolve_tenant_manager_address" \
  "$ROOT/backend-api/app/api/routes/customer_agent_packages.py" \
  && pass "customer packages use appliance manager resolver" \
  || fail "customer packages missing resolver"

grep -Fq "agent_inventory" \
  "$ROOT/backend-api/app/schemas/appliance_agent.py" \
  && pass "heartbeat schema accepts agent_inventory" \
  || fail "agent_inventory missing from schema"

grep -Fq "pending_jobs" \
  "$ROOT/backend-api/app/schemas/appliance_agent.py" \
  && pass "heartbeat response includes pending_jobs" \
  || fail "pending_jobs missing"

grep -Fq "claim_pending_jobs" \
  "$ROOT/backend-api/app/api/routes/appliance_agent.py" \
  && pass "heartbeat claims appliance jobs" \
  || fail "heartbeat missing job claim"

grep -Fq "_queue_appliance_ar_job" \
  "$ROOT/backend-api/app/services/edr_actions.py" \
  && pass "EDR routes isolate via appliance jobs" \
  || fail "EDR missing appliance job queue"

grep -Fq "enabled_services" \
  "$ROOT/backend-api/app/schemas/appliances.py" \
  && pass "ApplianceDetail exposes enabled_services" \
  || fail "enabled_services missing from ApplianceDetail"

grep -Fq "Enabled services" \
  "$ROOT/frontend-admin/src/pages/AppliancesPage.tsx" \
  && pass "Admin UI shows enabled services" \
  || fail "Admin UI missing enabled services"

grep -Fq 'cmd_register' \
  "$ROOT/kevantic-appliance/cli/kevantic-cli/kevantic_cli/cli.py" \
  && pass "kevantic-cli register wired" \
  || fail "cli register missing"

# Live DB migration present
if docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
  psql -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" -c "\d appliance_jobs" >/tmp/appliance_jobs_desc.txt 2>/dev/null; then
  grep -q "job_type" /tmp/appliance_jobs_desc.txt && pass "DB table appliance_jobs exists" \
    || fail "appliance_jobs table incomplete"
else
  fail "could not describe appliance_jobs (is postgres up? migration applied?)"
fi

if docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
  psql -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" -tAc "SELECT 1 FROM information_schema.columns WHERE table_name='appliances' AND column_name='enabled_services';" \
  | grep -q 1; then
  pass "appliances.enabled_services column exists"
else
  fail "appliances.enabled_services column missing"
fi

# Python import smoke inside backend container
if docker compose -f "$ROOT/docker-compose.yml" exec -T backend-api \
  python -c "from app.services.appliance_manager_resolver import resolve_tenant_manager_address; from app.services.appliance_jobs import enqueue_job; from app.services.appliance_agent_inventory import sync_appliance_agent_inventory; print('OK')" \
  2>/dev/null | grep -q OK; then
  pass "backend imports appliance track-1 modules"
else
  fail "backend import smoke failed"
fi

# Health
curl -fsS http://localhost:8000/health >/dev/null && pass "/health OK" || fail "/health"

# OpenAPI paths
OA="$(curl -fsS http://localhost:8000/openapi.json)"
echo "$OA" | grep -q '/appliance/jobs/{job_id}/ack' && pass "OpenAPI has job ack" || fail "OpenAPI missing job ack"
echo "$OA" | grep -q '/appliance/heartbeat' && pass "OpenAPI has heartbeat" || fail "OpenAPI missing heartbeat"

"$ROOT/scripts/kb093b_validate_kevantic_cli_b1.sh" >/tmp/kb093b-track1.txt
tail -1 /tmp/kb093b-track1.txt | grep -q PASSED && pass "kb093b CLI validator" || fail "kb093b CLI validator"

if [[ "$FAIL" -ne 0 ]]; then
  echo "APPLIANCE_TRACK1_VALIDATE_FAILED"
  exit 1
fi
echo "APPLIANCE_TRACK1_VALIDATE_OK"
