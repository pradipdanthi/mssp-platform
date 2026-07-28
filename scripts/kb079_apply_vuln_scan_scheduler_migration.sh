#!/usr/bin/env bash
# KB-079: Apply scheduler column on live PostgreSQL (additive).
set -euo pipefail
cd /opt/mssp-control
docker compose exec -T postgres psql -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
  -f - < postgres/init/013_kb079_vuln_scan_scheduler.sql
echo "KB-079 scheduler migration applied."
