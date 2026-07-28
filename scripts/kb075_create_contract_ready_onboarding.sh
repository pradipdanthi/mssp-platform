#!/usr/bin/env bash
# KB-075: Apply contract-ready onboarding columns to live Postgres.
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
DB_USER="mssp_admin"
DB_NAME="mssp_control"
cd "$PROJECT_DIR"
echo "Applying KB-075 contract-ready onboarding..."
docker compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" \
  < postgres/init/011_kb075_contract_ready_onboarding.sql
echo "KB-075 contract-ready onboarding schema applied."
