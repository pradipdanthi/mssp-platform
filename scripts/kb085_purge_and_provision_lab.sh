#!/usr/bin/env bash
# KB-085: Purge lab data, apply audit migration, provision Alpha-Win + Beta-Linux tenants.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API="${MSSP_API_BASE:-http://localhost:8000}"
PASS="${LAB_ADMIN_PASSWORD:-TempPass123!}"
PLATFORM_EMAIL="${PLATFORM_ADMIN_EMAIL:-platform.admin@example.local}"
PLATFORM_PASS="${PLATFORM_ADMIN_PASSWORD:-}"

echo "==> Apply audit enrichment migration"
docker exec -i mssp-postgres psql -U mssp_admin -d mssp_control \
  < "$ROOT/postgres/init/016_kb085_audit_enrichment.sql"

echo "==> Purge test/operational data"
python3 "$ROOT/scripts/purge_test_data.py" --via-docker --yes

echo "==> Ensure platform admin password for lab automation"
docker compose exec -T backend-api python - <<PY
from app.core.security import hash_password
from app.db.session import fetch_one_write
email = "${PLATFORM_EMAIL}"
password = """${PLATFORM_PASS:-TempPass123!}"""
row = fetch_one_write(
    "UPDATE platform_users SET password_hash = %s, status = 'active' WHERE email = %s RETURNING email;",
    (hash_password(password), email),
)
print("platform_admin_ready", row.get("email") if row else "MISSING")
PY
PLATFORM_PASS="${PLATFORM_PASS:-TempPass123!}"

echo "==> Login as platform admin"
TOKEN="$(curl -fsS -X POST "$API/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$PLATFORM_EMAIL\",\"password\":\"$PLATFORM_PASS\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"

auth=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')

create_tenant() {
  local name="$1" code="$2" email="$3" full="$4" phone="$5" notes="$6"
  curl -fsS -X POST "$API/admin/tenants" "${auth[@]}" -d "$(python3 - <<PY
import json
print(json.dumps({
  "name": "$name",
  "short_code": "$code",
  "status": "active",
  "sla_level": "business",
  "business_criticality": "high",
  "timezone": "Asia/Kolkata",
  "notes": "$notes",
  "deployment_mode": "on_prem_direct",
  "primary_contact_name": "$full",
  "primary_contact_email": "$email",
  "primary_contact_phone": "$phone",
  "country": "India",
  "portal_admin": {
    "email": "$email",
    "full_name": "$full",
    "password": "$PASS",
    "phone": "$phone",
  },
  "entitlements": {
    "wazuh_siem": True,
    "wazuh_retention_days": 90,
    "thehive_mode": "full",
    "greenbone_enabled": True,
    "greenbone_cadence": "monthly",
    "shuffle_mode": "standard",
    "zeek_enabled": True,
    "misp_enabled": False,
    "velociraptor_enabled": False,
  },
}))
PY
)"
}

echo "==> Onboard Alpha-Win-Corp"
ALPHA_JSON="$(create_tenant "Alpha-Win-Corp" "ALPHAWIN" "admin@alphawin.com" "Alpha Win Admin" "+91-9000000001" "Lab Windows endpoint tenant (agent 003)")"
echo "$ALPHA_JSON" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["id"], d["short_code"], d.get("onboard_result",{}).get("portal_user_email"))'

echo "==> Onboard Beta-Linux-Corp"
BETA_JSON="$(create_tenant "Beta-Linux-Corp" "BETALINUX" "admin@betalinux.com" "Beta Linux Admin" "+91-9000000002" "Lab Linux endpoint tenant (agent 001)")"
echo "$BETA_JSON" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["id"], d["short_code"], d.get("onboard_result",{}).get("portal_user_email"))'

echo "==> Assign Wazuh agents to tenant groups (best-effort)"
docker compose exec -T backend-api python - <<'PY' || true
from app.services import wazuh_client
from app.services.tenant_engine_provisioner import wazuh_group_for
for agent_id, code in (("003", "ALPHAWIN"), ("001", "BETALINUX")):
    group = wazuh_group_for(code)
    try:
        wazuh_client.ensure_agent_group(group)
        wazuh_client.assign_agent_to_group(agent_id, group, force=True)
        st = wazuh_client.get_agent_status(agent_id)
        print(f"agent={agent_id} group={group} status={st.get('status')} name={st.get('name')}")
    except Exception as exc:
        print(f"agent={agent_id} assign_failed: {exc}")
PY

echo "==> Verify tenants + admins"
docker exec mssp-postgres psql -U mssp_admin -d mssp_control -c \
  "SELECT t.short_code, t.name, u.email, u.role FROM tenants t
   JOIN platform_users u ON u.tenant_id = t.id
   WHERE t.short_code IN ('ALPHAWIN','BETALINUX') ORDER BY t.short_code;"

echo "LAB_PROVISION_OK"
echo "Customer admins: admin@alphawin.com / admin@betalinux.com  password: (LAB_ADMIN_PASSWORD)"
