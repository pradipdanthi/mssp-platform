#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
API_SERVICE="backend-api"
DB_USER="mssp_admin"
DB_NAME="mssp_control"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-010: Create Auth/RBAC foundation (database migration + demo users)"
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
  || fail "bcrypt is not installed in the backend-api container yet. Run 'docker compose build backend-api && docker compose up -d backend-api' first, then re-run this script."

section "2. Enter demo passwords (input is hidden, never displayed or logged)"

read -rs -p "Enter a password for demo SOC user (soc.manager@example.local): " SOC_PASSWORD
echo
read -rs -p "Confirm that password: " SOC_PASSWORD_CONFIRM
echo
[ "$SOC_PASSWORD" = "$SOC_PASSWORD_CONFIRM" ] || fail "SOC password entries did not match."
[ -n "$SOC_PASSWORD" ] || fail "SOC password cannot be empty."

read -rs -p "Enter a password for demo customer user (customer.viewer@demo.local): " CUST_PASSWORD
echo
read -rs -p "Confirm that password: " CUST_PASSWORD_CONFIRM
echo
[ "$CUST_PASSWORD" = "$CUST_PASSWORD_CONFIRM" ] || fail "Customer password entries did not match."
[ -n "$CUST_PASSWORD" ] || fail "Customer password cannot be empty."

unset SOC_PASSWORD_CONFIRM CUST_PASSWORD_CONFIRM

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

SOC_HASH="$(hash_password "$SOC_PASSWORD")"
CUST_HASH="$(hash_password "$CUST_PASSWORD")"

unset SOC_PASSWORD CUST_PASSWORD

[ -n "$SOC_HASH" ] || fail "Failed to compute SOC password hash."
[ -n "$CUST_HASH" ] || fail "Failed to compute customer password hash."

echo "Password hashes computed successfully (values are not displayed)."

section "4. Applying database migration (password_hash column + role rename)"

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
BEGIN;

ALTER TABLE platform_users ADD COLUMN IF NOT EXISTS password_hash TEXT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'platform_users_role_check'
    ) THEN
        ALTER TABLE platform_users DROP CONSTRAINT platform_users_role_check;
    END IF;
END $$;

UPDATE platform_users SET role = 'platform_admin' WHERE role = 'super_admin';

ALTER TABLE platform_users
    ADD CONSTRAINT platform_users_role_check
    CHECK (role IN ('platform_admin', 'soc_manager', 'soc_analyst', 'customer_admin', 'customer_viewer'));

COMMIT;
SQL

echo "Schema migration applied."

section "5. Seeding/updating demo login accounts"

[ -n "${SOC_HASH:-}" ] || fail "Internal error: SOC_HASH is empty before seeding."
[ -n "${CUST_HASH:-}" ] || fail "Internal error: CUST_HASH is empty before seeding."

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  -v soc_hash="$SOC_HASH" -v cust_hash="$CUST_HASH" <<'SQL'
BEGIN;

INSERT INTO platform_users (email, full_name, user_type, role, status, password_hash)
VALUES ('soc.manager@example.local', 'Demo SOC Manager', 'admin', 'soc_manager', 'active', :'soc_hash')
ON CONFLICT (email) DO UPDATE
    SET password_hash = EXCLUDED.password_hash,
        updated_at = now();

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM tenants WHERE short_code = 'DEMO') THEN
        RAISE EXCEPTION 'Required tenant DEMO does not exist. Run the KB-007 foundation seed first.';
    END IF;
END $$;

INSERT INTO platform_users (tenant_id, email, full_name, user_type, role, status, password_hash)
SELECT t.id, 'customer.viewer@demo.local', 'Demo Customer Viewer', 'customer', 'customer_viewer', 'active', :'cust_hash'
FROM tenants t
WHERE t.short_code = 'DEMO'
ON CONFLICT (email) DO UPDATE
    SET password_hash = EXCLUDED.password_hash,
        tenant_id = EXCLUDED.tenant_id,
        updated_at = now();

COMMIT;
SQL

unset SOC_HASH CUST_HASH

echo "Demo accounts ready."

section "6. Verification (no password values shown)"

docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -c "
SELECT email, role, user_type, tenant_id, status, (password_hash IS NOT NULL) AS has_password
FROM platform_users
WHERE email IN ('soc.manager@example.local', 'customer.viewer@demo.local')
ORDER BY email;
"

echo
echo "======================================================================"
echo "KB-010 auth/RBAC database setup completed."
echo "Next step: run ./scripts/kb010_validate_auth_rbac.sh"
echo "======================================================================"
