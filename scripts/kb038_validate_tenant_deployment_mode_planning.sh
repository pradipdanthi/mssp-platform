#!/usr/bin/env bash
# KB-038: Validate Tenant Deployment Mode Planning (docs only).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-038: Validate Tenant Deployment Mode Planning"
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
  "docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md"
  "scripts/kb038_validate_tenant_deployment_mode_planning.sh"
  "docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md"
  "docs/AI_PROMPT_LEDGER.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-038 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-038 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB038 planning doc required mentions"

file_mentions docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md \
  "deployment_mode" \
  "cloud" \
  "on_prem" \
  "hybrid" \
  "primary_cluster_id" \
  "deployment_role" \
  "cloud_collector" \
  "on_prem_appliance" \
  "metadata" \
  "raw logs" \
  "never" \
  "KB-037" \
  "soc_clusters" \
  "source_platform" \
  "admin" \
  "customer portal" \
  "no secrets"
echo "OK: KB038 doc mentions deployment modes, routing rules, and safety boundaries."

section "4. CONTEXT.md notes KB-038 planning"

file_mentions CONTEXT.md \
  "KB-038" \
  "deployment mode" \
  "hybrid" \
  "KB-037"
echo "OK: CONTEXT.md references KB-038 planning."

section "5. AI_PROMPT_LEDGER.md mentions KB-038"

file_mentions docs/AI_PROMPT_LEDGER.md \
  "KB-038" \
  "deployment_mode" \
  "hybrid"
echo "OK: ledger mentions KB-038."

section "6. No obvious secrets in KB-038 docs"

DOC_SCAN_FILES=(
  docs/KB038_TENANT_DEPLOYMENT_MODE_PLANNING.md
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
  fail "Possible secret material found in KB-038 documentation files"
fi
echo "OK: no obvious secret assignments in KB-038 docs."

section "7. Final verdict"

echo "======================================================================"
echo "KB-038 TENANT DEPLOYMENT MODE PLANNING VALIDATION PASSED"
echo "======================================================================"
