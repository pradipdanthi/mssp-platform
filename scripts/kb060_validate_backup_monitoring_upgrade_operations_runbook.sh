#!/usr/bin/env bash
# KB-060: Validate Backup, Monitoring, Upgrade, and Operations Runbook (docs only).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-060: Validate Backup, Monitoring, Upgrade, and Operations Runbook"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1" >&2
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

file_mentions() {
  local file="$1"
  shift
  local needle
  for needle in "$@"; do
    grep -qi "$needle" "$file" || fail "$file missing required mention: $needle"
  done
}

section "1. Required documentation files exist"

REQUIRED=(
  "docs/KB060_BACKUP_MONITORING_UPGRADE_OPERATIONS_RUNBOOK.md"
  "scripts/kb060_validate_backup_monitoring_upgrade_operations_runbook.sh"
  "docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md"
  "docs/KB059_MULTI_CLUSTER_CAPACITY_CUSTOMER_PLACEMENT.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" 2>/dev/null || fail "$p has working-tree changes but KB-060 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" 2>/dev/null || fail "$p has staged changes but KB-060 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB060 runbook required mentions"

file_mentions docs/KB060_BACKUP_MONITORING_UPGRADE_OPERATIONS_RUNBOOK.md \
  "Purpose" \
  "VM 111" \
  "monitoring" \
  "Prometheus" \
  "Grafana" \
  "backup" \
  "restore" \
  "PostgreSQL" \
  "postgres" \
  "control plane" \
  "upgrade" \
  "Proxmox" \
  "snapshot" \
  "Phase 12" \
  "KB-036" \
  "no secrets" \
  "customer portal"
echo "OK: KB060 doc mentions monitoring, backup/restore, upgrade, Proxmox snapshots, Phase 12, and safety."

section "4. KB060 builds on KB-036 Phase 12"

file_mentions docs/KB060_BACKUP_MONITORING_UPGRADE_OPERATIONS_RUNBOOK.md \
  "KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP" \
  "Phase 12"
echo "OK: KB060 references KB-036 Phase 12."

section "5. No obvious secrets in KB-060 docs"

DOC_SCAN_FILES=(
  docs/KB060_BACKUP_MONITORING_UPGRADE_OPERATIONS_RUNBOOK.md
)

SECRET_HIT="$(grep -REn \
  -e 'password[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{6,}' \
  -e 'api_key[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{6,}' \
  -e 'token[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{8,}' \
  -e 'JWT_SECRET[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]+' \
  -e 'Bearer[[:space:]]+[A-Za-z0-9_-]{20,}' \
  "${DOC_SCAN_FILES[@]}" 2>/dev/null || true)"

if [ -n "$SECRET_HIT" ]; then
  echo "$SECRET_HIT" >&2
  fail "Possible secret material found in KB-060 documentation files"
fi
echo "OK: no obvious secret assignments in KB-060 docs."

section "6. Final verdict"

echo "======================================================================"
echo "KB-060 BACKUP MONITORING UPGRADE OPERATIONS RUNBOOK VALIDATION PASSED"
echo "======================================================================"
