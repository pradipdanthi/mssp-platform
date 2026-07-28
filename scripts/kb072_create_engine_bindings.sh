#!/usr/bin/env bash
# KB-072: Apply tenant_engine_bindings schema to live Postgres.
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
DB_USER="mssp_admin"
DB_NAME="mssp_control"
cd "$PROJECT_DIR"
echo "Applying KB-072 tenant_engine_bindings..."
docker compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  < postgres/init/007_kb072_tenant_engine_bindings.sql
echo "KB-072 tenant_engine_bindings schema applied."
