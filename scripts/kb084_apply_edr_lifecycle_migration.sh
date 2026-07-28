#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SQL="$ROOT/postgres/init/015_kb084_edr_lifecycle_forensics.sql"
docker exec -i mssp-postgres psql -U mssp_admin -d mssp_control < "$SQL"
echo "KB-084 EDR lifecycle / forensics migration applied."
