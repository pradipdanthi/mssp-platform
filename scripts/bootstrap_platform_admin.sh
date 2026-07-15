#!/usr/bin/env bash
# KB-020: Create the first platform_admin for a fresh deployment.
# Does not seed demo tenants/users. Does not print passwords or hashes.
# Do not run this script automatically from docker-compose.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
API_SERVICE="backend-api"
DB_USER="${POSTGRES_USER:-mssp_admin}"
DB_NAME="${POSTGRES_DB:-mssp_control}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/bootstrap_platform_admin.sh [--force]

Creates the first platform_admin user (tenant_id NULL) for a fresh database.
Does NOT create demo tenants, demo customers, or example.local users.

Password handling:
  - Prefer interactive hidden prompts (password entered twice).
  - Or set environment variables for non-interactive automation:
      BOOTSTRAP_ADMIN_EMAIL
      BOOTSTRAP_ADMIN_FULL_NAME
      BOOTSTRAP_ADMIN_PASSWORD
  - Passwords and password hashes are never printed.
  - There is no default password in this script.

Options:
  --force          Allow creating another platform_admin even if one exists
  -h, --help       Show this help

This script must be run manually. It is not started by Docker Compose.
EOF
}

FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-020: bootstrap_platform_admin.sh"
echo "Creates the first platform_admin (no demo data)."
echo "======================================================================"

fail() {
  echo
  echo "FAILED: $1" >&2
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

cleanup_secrets() {
  unset BOOTSTRAP_ADMIN_PASSWORD ADMIN_PASSWORD ADMIN_PASSWORD_CONFIRM ADMIN_HASH 2>/dev/null || true
}
trap cleanup_secrets EXIT

section "1. Pre-flight checks"

[ -f docker-compose.yml ] || fail "docker-compose.yml not found in $PROJECT_DIR"
docker compose ps "$DB_SERVICE" >/dev/null 2>&1 || fail "Postgres service is not available via docker compose"
docker compose ps "$API_SERVICE" >/dev/null 2>&1 || fail "backend-api service is not available via docker compose"
docker compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null \
  || fail "PostgreSQL is not ready"
docker compose exec -T "$API_SERVICE" python3 -c "from app.core.security import hash_password" \
  || fail "Cannot import app.core.security.hash_password inside backend-api (is the container running?)"

section "2. Existing platform_admin check"

EXISTING_COUNT="$(docker compose exec -T "$DB_SERVICE" psql -X -q -t -A \
  -U "$DB_USER" -d "$DB_NAME" \
  -c "SELECT count(*) FROM platform_users WHERE role = 'platform_admin';" \
  | tr -d '[:space:]')"

[ -n "$EXISTING_COUNT" ] || fail "Could not query existing platform_admin count"

if [ "$EXISTING_COUNT" != "0" ] && [ "$FORCE" -ne 1 ]; then
  fail "A platform_admin user already exists (count=$EXISTING_COUNT). Refusing to continue. Re-run with --force only if you intentionally need another platform_admin."
fi

if [ "$EXISTING_COUNT" != "0" ] && [ "$FORCE" -eq 1 ]; then
  echo "WARNING: --force set; a platform_admin already exists (count=$EXISTING_COUNT). Proceeding to insert another."
fi

section "3. Collect admin identity (password never echoed)"

ADMIN_EMAIL="${BOOTSTRAP_ADMIN_EMAIL:-}"
ADMIN_FULL_NAME="${BOOTSTRAP_ADMIN_FULL_NAME:-}"
ADMIN_PASSWORD="${BOOTSTRAP_ADMIN_PASSWORD:-}"

if [ -z "$ADMIN_EMAIL" ]; then
  read -r -p "Admin email: " ADMIN_EMAIL
fi
[ -n "$ADMIN_EMAIL" ] || fail "Admin email cannot be empty"

if [ -z "$ADMIN_FULL_NAME" ]; then
  read -r -p "Admin full name: " ADMIN_FULL_NAME
fi
[ -n "$ADMIN_FULL_NAME" ] || fail "Admin full name cannot be empty"

if [ -z "$ADMIN_PASSWORD" ]; then
  read -rs -p "Admin password (input hidden): " ADMIN_PASSWORD
  echo
  read -rs -p "Confirm admin password (input hidden): " ADMIN_PASSWORD_CONFIRM
  echo
  [ "$ADMIN_PASSWORD" = "$ADMIN_PASSWORD_CONFIRM" ] || fail "Password entries did not match"
  unset ADMIN_PASSWORD_CONFIRM
else
  echo "Using BOOTSTRAP_ADMIN_PASSWORD from the environment (value not displayed)."
fi

[ -n "$ADMIN_PASSWORD" ] || fail "Admin password cannot be empty"
[ "${#ADMIN_PASSWORD}" -ge 12 ] || fail "Admin password must be at least 12 characters"

section "4. Hash password with app.core.security.hash_password (bcrypt)"

# Same approved hashing path used by the API (never log plaintext or hash).
ADMIN_HASH="$(printf '%s\n' "$ADMIN_PASSWORD" | docker compose exec -T "$API_SERVICE" python3 -c '
from app.core.security import hash_password
import sys
plain = sys.stdin.readline().rstrip("\n")
print(hash_password(plain), end="")
')"

unset ADMIN_PASSWORD
[ -n "$ADMIN_HASH" ] || fail "Failed to compute password hash"
echo "Password hash computed successfully (value is not displayed)."

section "5. Insert platform_admin (tenant_id NULL)"

# Pass identity/hash as psql variables; never echo the hash.
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  -v admin_email="$ADMIN_EMAIL" \
  -v admin_full_name="$ADMIN_FULL_NAME" \
  -v admin_hash="$ADMIN_HASH" <<'SQL'
BEGIN;

INSERT INTO platform_users (
    email,
    full_name,
    user_type,
    role,
    status,
    tenant_id,
    password_hash
) VALUES (
    :'admin_email',
    :'admin_full_name',
    'admin',
    'platform_admin',
    'active',
    NULL,
    :'admin_hash'
);

COMMIT;
SQL

unset ADMIN_HASH

section "6. Verify (no secrets shown)"

docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" \
  -v admin_email="$ADMIN_EMAIL" <<'SQL'
SELECT email, full_name, role, user_type, tenant_id, status,
       (password_hash IS NOT NULL) AS has_password
FROM platform_users
WHERE email = :'admin_email';
SQL

echo
echo "Bootstrap complete. You can sign in to the admin portal with the email you provided."
echo "No demo tenants or demo users were created by this script."
exit 0
