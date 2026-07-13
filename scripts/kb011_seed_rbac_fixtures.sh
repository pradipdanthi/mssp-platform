#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
API_SERVICE="backend-api"
DB_USER="mssp_admin"
DB_NAME="mssp_control"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-011: Seed RBAC fixtures (second demo tenant + missing demo users)"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "FAILED: $1"
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

section "1. Pre-flight checks"

[ -f docker-compose.yml ] || fail "docker-compose.yml not found. Run this from $PROJECT_DIR."

docker compose ps "$DB_SERVICE" >/dev/null 2>&1 || fail "Postgres service is not available via docker compose."
docker compose ps "$API_SERVICE" >/dev/null 2>&1 || fail "backend-api service is not available via docker compose."

echo "Checking PostgreSQL connectivity..."
docker compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME" \
  || fail "PostgreSQL is not ready."

echo "Checking that backend-api has the bcrypt package installed..."
docker compose exec -T "$API_SERVICE" python3 -c "import bcrypt" \
  || fail "bcrypt is not installed in the backend-api container. Run 'docker compose build backend-api && docker compose up -d backend-api' first if you have not already, then re-run this script."

echo "Checking that the DEMO tenant already exists (required baseline)..."
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" -tAc \
  "SELECT 1 FROM tenants WHERE short_code = 'DEMO';" | grep -q 1 \
  || fail "Required tenant DEMO does not exist. Run the KB-007 foundation seed first."

section "2. Enter demo passwords (input is hidden, never displayed or logged)"

read -rs -p "Enter a password for demo platform_admin user (platform.admin@example.local): " PLATFORM_ADMIN_PASSWORD
echo
read -rs -p "Confirm that password: " PLATFORM_ADMIN_PASSWORD_CONFIRM
echo
[ "$PLATFORM_ADMIN_PASSWORD" = "$PLATFORM_ADMIN_PASSWORD_CONFIRM" ] || fail "platform_admin password entries did not match."
[ -n "$PLATFORM_ADMIN_PASSWORD" ] || fail "platform_admin password cannot be empty."

read -rs -p "Enter a password for demo soc_analyst user (soc.analyst@example.local): " SOC_ANALYST_PASSWORD
echo
read -rs -p "Confirm that password: " SOC_ANALYST_PASSWORD_CONFIRM
echo
[ "$SOC_ANALYST_PASSWORD" = "$SOC_ANALYST_PASSWORD_CONFIRM" ] || fail "soc_analyst password entries did not match."
[ -n "$SOC_ANALYST_PASSWORD" ] || fail "soc_analyst password cannot be empty."

read -rs -p "Enter a password for demo customer_admin user (customer.admin@demo2.local): " CUSTOMER_ADMIN_PASSWORD
echo
read -rs -p "Confirm that password: " CUSTOMER_ADMIN_PASSWORD_CONFIRM
echo
[ "$CUSTOMER_ADMIN_PASSWORD" = "$CUSTOMER_ADMIN_PASSWORD_CONFIRM" ] || fail "customer_admin password entries did not match."
[ -n "$CUSTOMER_ADMIN_PASSWORD" ] || fail "customer_admin password cannot be empty."

unset PLATFORM_ADMIN_PASSWORD_CONFIRM SOC_ANALYST_PASSWORD_CONFIRM CUSTOMER_ADMIN_PASSWORD_CONFIRM

section "3. Hashing passwords with bcrypt (plaintext is never stored or printed)"

hash_password() {
  local plain="$1"
  docker compose exec -T "$API_SERVICE" python3 -c '
import bcrypt
import sys
plain = sys.stdin.readline().rstrip("\n").encode("utf-8")
print(bcrypt.hashpw(plain, bcrypt.gensalt()).decode("utf-8"))
' <<< "$plain"
}

PLATFORM_ADMIN_HASH="$(hash_password "$PLATFORM_ADMIN_PASSWORD")"
SOC_ANALYST_HASH="$(hash_password "$SOC_ANALYST_PASSWORD")"
CUSTOMER_ADMIN_HASH="$(hash_password "$CUSTOMER_ADMIN_PASSWORD")"

unset PLATFORM_ADMIN_PASSWORD SOC_ANALYST_PASSWORD CUSTOMER_ADMIN_PASSWORD

[ -n "$PLATFORM_ADMIN_HASH" ] || fail "Failed to compute platform_admin password hash."
[ -n "$SOC_ANALYST_HASH" ] || fail "Failed to compute soc_analyst password hash."
[ -n "$CUSTOMER_ADMIN_HASH" ] || fail "Failed to compute customer_admin password hash."

echo "Password hashes computed successfully (values are not displayed)."

section "4. Creating the second demo tenant (DEMO2) — clearly fake, validation-only"

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
BEGIN;

INSERT INTO tenants (name, short_code, status, sla_level, business_criticality, timezone, notes)
VALUES (
    'Demo Tenant Two (KB-011 Validation)',
    'DEMO2',
    'active',
    'standard',
    'medium',
    'Asia/Kolkata',
    'KB-011 fixture tenant used only for tenant-isolation validation testing. Not a real customer.'
)
ON CONFLICT (short_code) DO UPDATE
    SET updated_at = now();

COMMIT;
SQL

echo "DEMO2 tenant is present."

section "5. Seeding/updating demo login accounts"

[ -n "${PLATFORM_ADMIN_HASH:-}" ] || fail "Internal error: PLATFORM_ADMIN_HASH is empty before seeding."
[ -n "${SOC_ANALYST_HASH:-}" ] || fail "Internal error: SOC_ANALYST_HASH is empty before seeding."
[ -n "${CUSTOMER_ADMIN_HASH:-}" ] || fail "Internal error: CUSTOMER_ADMIN_HASH is empty before seeding."

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  -v platform_admin_hash="$PLATFORM_ADMIN_HASH" \
  -v soc_analyst_hash="$SOC_ANALYST_HASH" \
  -v customer_admin_hash="$CUSTOMER_ADMIN_HASH" <<'SQL'
BEGIN;

INSERT INTO platform_users (email, full_name, user_type, role, status, password_hash)
VALUES ('platform.admin@example.local', 'Demo Platform Admin', 'admin', 'platform_admin', 'active', :'platform_admin_hash')
ON CONFLICT (email) DO UPDATE
    SET password_hash = EXCLUDED.password_hash,
        updated_at = now();

INSERT INTO platform_users (email, full_name, user_type, role, status, password_hash)
VALUES ('soc.analyst@example.local', 'Demo SOC Analyst', 'admin', 'soc_analyst', 'active', :'soc_analyst_hash')
ON CONFLICT (email) DO UPDATE
    SET password_hash = EXCLUDED.password_hash,
        updated_at = now();

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM tenants WHERE short_code = 'DEMO2') THEN
        RAISE EXCEPTION 'Required tenant DEMO2 does not exist. This should not happen after step 4 above.';
    END IF;
END $$;

INSERT INTO platform_users (tenant_id, email, full_name, user_type, role, status, password_hash)
SELECT t.id, 'customer.admin@demo2.local', 'Demo Customer Admin (Tenant Two)', 'customer', 'customer_admin', 'active', :'customer_admin_hash'
FROM tenants t
WHERE t.short_code = 'DEMO2'
ON CONFLICT (email) DO UPDATE
    SET password_hash = EXCLUDED.password_hash,
        tenant_id = EXCLUDED.tenant_id,
        updated_at = now();

COMMIT;
SQL

unset PLATFORM_ADMIN_HASH SOC_ANALYST_HASH CUSTOMER_ADMIN_HASH

echo "Demo accounts ready."

section "6. Verification (no password values shown)"

echo "Tenants:"
docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -c "
SELECT short_code, name, status
FROM tenants
WHERE short_code IN ('DEMO', 'DEMO2')
ORDER BY short_code;
"

echo
echo "Demo users:"
docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -c "
SELECT email, role, user_type, tenant_id, status, (password_hash IS NOT NULL) AS has_password
FROM platform_users
WHERE email IN (
    'platform.admin@example.local',
    'soc.manager@example.local',
    'soc.analyst@example.local',
    'customer.admin@demo2.local',
    'customer.viewer@demo.local'
)
ORDER BY email;
"

echo
echo "======================================================================"
echo "KB-011 RBAC fixture setup completed."
echo "Next step: run ./scripts/kb011_validate_protected_apis.sh"
echo "======================================================================"
