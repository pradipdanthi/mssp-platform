#!/usr/bin/env bash
# Apply KB-071b roadmap entitlement columns.
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
DB_USER="mssp_admin"
DB_NAME="mssp_control"
cd "$PROJECT_DIR"
docker compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  < postgres/init/006_kb071b_entitlement_roadmap_modules.sql
echo "KB-071b roadmap entitlement columns applied."
