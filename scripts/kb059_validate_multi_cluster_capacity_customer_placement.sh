#!/usr/bin/env bash
# KB-059: Validate Multi-Cluster Capacity and Customer Placement (docs only).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-059: Validate Multi-Cluster Capacity and Customer Placement"
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
  "docs/KB059_MULTI_CLUSTER_CAPACITY_CUSTOMER_PLACEMENT.md"
  "scripts/kb059_validate_multi_cluster_capacity_customer_placement.sh"
  "docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md"
  "docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md"
  "docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" 2>/dev/null || fail "$p has working-tree changes but KB-059 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" 2>/dev/null || fail "$p has staged changes but KB-059 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB059 planning doc required mentions"

file_mentions docs/KB059_MULTI_CLUSTER_CAPACITY_CUSTOMER_PLACEMENT.md \
  "Purpose" \
  "soc_clusters" \
  "capacity" \
  "agents" \
  "EPS" \
  "storage" \
  "retention" \
  "placement" \
  "primary_cluster_id" \
  "no fixed customer count" \
  "admin-only" \
  "no secrets" \
  "KB-037" \
  "KB-038" \
  "customer portal" \
  "deployment_mode"
echo "OK: KB059 doc mentions capacity, placement, primary_cluster_id, KB-037/038, and safety boundaries."

section "4. KB059 builds on KB-037 and KB-038"

file_mentions docs/KB059_MULTI_CLUSTER_CAPACITY_CUSTOMER_PLACEMENT.md \
  "KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING" \
  "KB038_TENANT_DEPLOYMENT_MODE_PLANNING"
echo "OK: KB059 references KB-037 and KB-038 planning docs."

section "5. No obvious secrets in KB-059 docs"

DOC_SCAN_FILES=(
  docs/KB059_MULTI_CLUSTER_CAPACITY_CUSTOMER_PLACEMENT.md
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
  fail "Possible secret material found in KB-059 documentation files"
fi
echo "OK: no obvious secret assignments in KB-059 docs."

section "6. Final verdict"

echo "======================================================================"
echo "KB-059 MULTI-CLUSTER CAPACITY CUSTOMER PLACEMENT VALIDATION PASSED"
echo "======================================================================"
