#!/usr/bin/env bash
# KB-020: Optional development/lab demo seed orchestrator.
# NEVER run this against production. NEVER mount postgres/seed/dev into
# docker-entrypoint-initdb.d. This script does not delete database rows.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
SEED_DIR="$PROJECT_DIR/postgres/seed/dev"
SEED_SQL="$SEED_DIR/001_demo_seed.sql"
DB_SERVICE="postgres"
DB_USER="${POSTGRES_USER:-mssp_admin}"
DB_NAME="${POSTGRES_DB:-mssp_control}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/seed_demo_data.sh --yes-dev-demo

DEVELOPMENT / LAB ONLY.

Loads optional demo seed SQL from postgres/seed/dev/ when present.
Refuses to run when APP_ENV=production.
Requires the explicit confirmation flag --yes-dev-demo.

This script:
  - does not run automatically
  - is not called by docker-compose
  - does not delete data
  - does not print secrets

Options:
  --yes-dev-demo   Required confirmation that this is a development/lab run
  -h, --help       Show this help

Environment:
  APP_ENV          If set to "production", the script exits with an error
EOF
}

YES_DEV_DEMO=0

while [ $# -gt 0 ]; do
  case "$1" in
    --yes-dev-demo)
      YES_DEV_DEMO=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-020: seed_demo_data.sh — DEVELOPMENT / LAB ONLY"
echo "======================================================================"
echo
echo "This orchestrator loads optional demo fixtures (DEMO / DEMO2 /"
echo "example.local users, demo alerts/incidents/tokens when present)."
echo "It must never be used for a production deployment."
echo

if [ "${APP_ENV:-}" = "production" ]; then
  echo "REFUSED: APP_ENV=production." >&2
  echo "Demo seed is blocked in production. Use scripts/bootstrap_platform_admin.sh" >&2
  echo "for the first platform_admin instead." >&2
  exit 1
fi

if [ "$YES_DEV_DEMO" -ne 1 ]; then
  echo "REFUSED: missing required confirmation flag --yes-dev-demo." >&2
  echo >&2
  usage >&2
  exit 1
fi

if [ ! -f "$SEED_SQL" ]; then
  echo "Demo seed reconstruction is deferred (KB-020)."
  echo
  echo "No file found at:"
  echo "  $SEED_SQL"
  echo
  echo "postgres/seed/dev/README.md explains why a consolidated SQL seed was"
  echo "not inventored blindly from historical KB-007 foundations."
  echo
  echo "For the current lab, existing demo rows (if any) remain untouched."
  echo "Historical lab scripts under scripts/kb007_*, kb010_create_auth_rbac.sh"
  echo "(demo user sections), and kb011_seed_rbac_fixtures.sh may still be used"
  echo "on disposable development environments only — never in production."
  echo
  echo "Exiting without applying any database changes."
  exit 1
fi

# Future path: when 001_demo_seed.sql exists, apply it idempotently.
echo "Found demo seed SQL: $SEED_SQL"
echo "Applying (development/lab only; no deletes performed by this script)..."

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" < "$SEED_SQL"

echo
echo "Demo seed SQL applied. Review the admin UI / validation suite on this lab."
echo "Remember: this data is for development and training only."
exit 0
