#!/usr/bin/env bash
# KB-069: Apply vulnerabilities schema migration to live Postgres.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
DB_USER="mssp_admin"
DB_NAME="mssp_control"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-069: Create vulnerabilities foundation (database migration)"
echo "======================================================================"

fail() { echo; echo "FAILED: $1"; exit 1; }
section() { echo; echo "----------------------------------------------------------------------"; echo "$1"; echo "----------------------------------------------------------------------"; }

section "1. Pre-flight"
[ -f docker-compose.yml ] || fail "docker-compose.yml not found"
[ -f postgres/init/004_kb069_vulnerabilities.sql ] || fail "migration SQL missing"
docker compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME" \
  || fail "PostgreSQL is not ready"

section "2. Apply migration"
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  < postgres/init/004_kb069_vulnerabilities.sql
echo "Schema migration applied."

section "3. Verify"
TABLE_OK="$(docker compose exec -T "$DB_SERVICE" psql -X -q -t -A -U "$DB_USER" -d "$DB_NAME" -c "
SELECT count(*) FROM information_schema.tables
WHERE table_schema='public' AND table_name='vulnerabilities';
")"
COL_OK="$(docker compose exec -T "$DB_SERVICE" psql -X -q -t -A -U "$DB_USER" -d "$DB_NAME" -c "
SELECT count(*) FROM information_schema.columns
WHERE table_name='customer_recommendations' AND column_name='related_vulnerability_id';
")"
[ "$TABLE_OK" = "1" ] || fail "vulnerabilities table missing"
[ "$COL_OK" = "1" ] || fail "related_vulnerability_id column missing"
echo "OK: vulnerabilities table + recommendation link column"

echo
echo "KB-069 CREATE VULNERABILITIES MIGRATION PASSED"
