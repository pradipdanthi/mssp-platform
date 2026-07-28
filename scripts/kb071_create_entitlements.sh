#!/usr/bin/env bash
# KB-071: Apply tenant_entitlements schema migration to live Postgres.
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
DB_USER="mssp_admin"
DB_NAME="mssp_control"
cd "$PROJECT_DIR"
echo "Applying KB-071 tenant_entitlements..."
docker compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  < postgres/init/005_kb071_tenant_entitlements.sql
echo "KB-071 entitlements schema applied."
