#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
DB_USER="mssp_admin"
DB_NAME="mssp_control"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-016: Create Appliance Registration/Heartbeat foundation (database migration)"
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

echo "Checking PostgreSQL connectivity..."
docker compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME" \
  || fail "PostgreSQL is not ready."

section "2. Applying database migration (appliance API key columns + constraint)"

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
BEGIN;

ALTER TABLE appliances ADD COLUMN IF NOT EXISTS appliance_api_key_hash TEXT;
ALTER TABLE appliances ADD COLUMN IF NOT EXISTS appliance_api_key_hint TEXT;
ALTER TABLE appliances ADD COLUMN IF NOT EXISTS appliance_key_created_at TIMESTAMPTZ;
ALTER TABLE appliances ADD COLUMN IF NOT EXISTS appliance_key_last_used_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'appliances_appliance_api_key_hash_key'
    ) THEN
        ALTER TABLE appliances
            ADD CONSTRAINT appliances_appliance_api_key_hash_key UNIQUE (appliance_api_key_hash);
    END IF;
END $$;

COMMIT;
SQL

echo "Schema migration applied."

section "3. Verification (columns and constraint exist; no data is displayed)"

echo "Columns on appliances matching 'appliance_%key%':"
docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -c "
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'appliances'
  AND column_name LIKE 'appliance_%key%'
ORDER BY column_name;
"

COLUMN_COUNT="$(docker compose exec -T "$DB_SERVICE" psql -X -q -t -A -U "$DB_USER" -d "$DB_NAME" -c "
SELECT count(*)
FROM information_schema.columns
WHERE table_name = 'appliances'
  AND column_name IN (
    'appliance_api_key_hash',
    'appliance_api_key_hint',
    'appliance_key_created_at',
    'appliance_key_last_used_at'
  );
" | tr -d '[:space:]')"

[ "$COLUMN_COUNT" = "4" ] || fail "Expected 4 new appliance credential columns, found $COLUMN_COUNT"
echo "OK: all 4 new columns exist."

echo
echo "Unique constraint check:"
docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -c "
SELECT conname
FROM pg_constraint
WHERE conname = 'appliances_appliance_api_key_hash_key';
"

CONSTRAINT_COUNT="$(docker compose exec -T "$DB_SERVICE" psql -X -q -t -A -U "$DB_USER" -d "$DB_NAME" -c "
SELECT count(*) FROM pg_constraint WHERE conname = 'appliances_appliance_api_key_hash_key';
" | tr -d '[:space:]')"

[ "$CONSTRAINT_COUNT" = "1" ] || fail "Expected unique constraint appliances_appliance_api_key_hash_key to exist, found $CONSTRAINT_COUNT"
echo "OK: unique constraint appliances_appliance_api_key_hash_key exists."

echo
echo "======================================================================"
echo "KB-016 database migration completed."
echo "Next step: rebuild/restart backend-api, then run"
echo "./scripts/kb016_validate_appliance_registration_heartbeat.sh"
echo "======================================================================"
