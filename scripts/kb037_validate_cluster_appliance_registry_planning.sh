#!/usr/bin/env bash
# KB-037: Validate Cluster and Appliance Registry Planning (docs only).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-037: Validate Cluster and Appliance Registry Planning"
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
  "docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md"
  "scripts/kb037_validate_cluster_appliance_registry_planning.sh"
  "docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md"
  "docs/AI_PROMPT_LEDGER.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-037 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-037 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB037 planning doc required mentions"

file_mentions docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md \
  "cluster registry" \
  "appliance registry" \
  "soc_clusters" \
  "primary_cluster_id" \
  "deployment_role" \
  "source_platform" \
  "sync_health_status" \
  "max_agents" \
  "eps_budget" \
  "storage_gb_budget" \
  "retention_days" \
  "tenant" \
  "cluster assignment" \
  "capacity" \
  "not a fixed customer count" \
  "KB-038" \
  "deployment_mode" \
  "admin-only" \
  "no secrets" \
  "extend existing" \
  "appliances"
echo "OK: KB037 doc mentions cluster/appliance registry design and deferrals."

section "4. CONTEXT.md notes KB-037 planning"

file_mentions CONTEXT.md \
  "KB-037" \
  "cluster registry" \
  "KB-036"
echo "OK: CONTEXT.md references KB-037 planning."

section "5. AI_PROMPT_LEDGER.md mentions KB-037"

file_mentions docs/AI_PROMPT_LEDGER.md \
  "KB-037" \
  "cluster" \
  "appliance registry"
echo "OK: ledger mentions KB-037."

section "6. No obvious secrets in KB-037 docs"

DOC_SCAN_FILES=(
  docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md
  docs/AI_PROMPT_LEDGER.md
  CONTEXT.md
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
  fail "Possible secret material found in KB-037 documentation files"
fi
echo "OK: no obvious secret assignments in KB-037 docs."

section "7. Final verdict"

echo "======================================================================"
echo "KB-037 CLUSTER APPLIANCE REGISTRY PLANNING VALIDATION PASSED"
echo "======================================================================"
