#!/usr/bin/env bash
# KB-073: Apply tenant deployment_mode / cloud_provider columns to live Postgres.
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
DB_USER="mssp_admin"
DB_NAME="mssp_control"
cd "$PROJECT_DIR"
echo "Applying KB-073 tenant deployment mode..."
docker compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  < postgres/init/008_kb073_tenant_deployment_mode.sql
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  < postgres/init/009_kb073b_cloud_appliance_mode.sql
echo "KB-073 tenant deployment mode schema applied (including cloud_appliance)."
