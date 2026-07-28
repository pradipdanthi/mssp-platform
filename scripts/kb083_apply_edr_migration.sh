#!/usr/bin/env bash
# Apply KB-083 EDR tables on an existing Postgres (idempotent).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SQL="$ROOT/postgres/init/014_kb083_edr_actions.sql"
docker exec -i mssp-postgres psql -U mssp_admin -d mssp_control < "$SQL"
echo "KB-083 EDR migration applied."
