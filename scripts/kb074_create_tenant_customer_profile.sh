#!/usr/bin/env bash
# KB-074: Apply tenant customer profile columns to live Postgres.
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
DB_USER="mssp_admin"
DB_NAME="mssp_control"
cd "$PROJECT_DIR"
echo "Applying KB-074 tenant customer profile..."
docker compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  < postgres/init/010_kb074_tenant_customer_profile.sql
echo "KB-074 tenant customer profile schema applied."
