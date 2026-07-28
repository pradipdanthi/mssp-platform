#!/usr/bin/env bash
# KB-072: validate tenant engine provisioning wiring (schema + code + API shapes).
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"

pass=0
fail=0
check() {
  local name="$1"
  shift
  if "$@"; then
    echo "PASS: $name"
    pass=$((pass + 1))
  else
    echo "FAIL: $name"
    fail=$((fail + 1))
  fi
}

file_exists() { [[ -f "$1" ]]; }
file_mentions() {
  local f="$1"; shift
  local needle
  for needle in "$@"; do
    grep -qF "$needle" "$f" || return 1
  done
  return 0
}

check "schema file" file_exists postgres/init/007_kb072_tenant_engine_bindings.sql
check "schema mentions bindings" file_mentions postgres/init/007_kb072_tenant_engine_bindings.sql \
  tenant_engine_bindings wazuh_agent_group thehive_tenant_tag
check "provisioner service" file_exists backend-api/app/services/tenant_engine_provisioner.py
check "wazuh client" file_exists backend-api/app/services/wazuh_client.py
check "thehive client" file_exists backend-api/app/services/thehive_client.py
check "tenant routes wired" file_mentions backend-api/app/api/routes/tenant_management.py \
  provision_tenant_engines engine-provision engine_binding
check "wazuh ingress tenant resolve" file_mentions backend-api/app/api/routes/soc_sync.py \
  resolve_short_code_by_wazuh_group
check "compose secrets mounts" file_mentions docker-compose.yml \
  THEHIVE_PASSWORD_FILE WAZUH_API_USER_FILE WAZUH_API_PASSWORD_FILE
check "admin API helpers" file_mentions frontend-admin/src/api/admin.ts \
  provisionTenantEngines TenantEngineBinding
check "tenants UI actions" file_mentions frontend-admin/src/pages/TenantsPage.tsx \
  "Engine binding / provision" "Provision all engines"
check "docs" file_exists docs/KB072_TENANT_ENGINE_PROVISIONING.md

# Live DB table
if docker compose exec -T postgres psql -U mssp_admin -d mssp_control -Atc \
  "SELECT to_regclass('public.tenant_engine_bindings');" | grep -q tenant_engine_bindings; then
  echo "PASS: live table tenant_engine_bindings"
  pass=$((pass + 1))
else
  echo "FAIL: live table tenant_engine_bindings"
  fail=$((fail + 1))
fi

# Backend import smoke (inside container)
if docker compose exec -T backend-api python -c \
  "from app.services.tenant_engine_provisioner import wazuh_group_for; assert wazuh_group_for('acme')=='tenant_ACME'"; then
  echo "PASS: backend provisioner import"
  pass=$((pass + 1))
else
  echo "FAIL: backend provisioner import"
  fail=$((fail + 1))
fi

echo "SUMMARY pass=$pass fail=$fail"
[[ "$fail" -eq 0 ]]
