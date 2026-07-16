#!/usr/bin/env bash
# KB-048: Validate Shuffle SOAR Deployment Plan (docs only).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-048: Validate Shuffle SOAR Deployment Plan"
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
  "docs/KB048_SHUFFLE_SOAR_DEPLOYMENT_PLAN.md"
  "scripts/kb048_validate_shuffle_soar_deployment_plan.sh"
  "docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md"
  "docs/KB047_THEHIVE_DEPLOYMENT_PLAN.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" 2>/dev/null || fail "$p has working-tree changes but KB-048 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" 2>/dev/null || fail "$p has staged changes but KB-048 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB048 planning doc required mentions"

file_mentions docs/KB048_SHUFFLE_SOAR_DEPLOYMENT_PLAN.md \
  "Shuffle" \
  "SOAR" \
  "VM 103" \
  "shuffle" \
  "playbook" \
  "webhook" \
  "tenant_id" \
  "tenant isolation" \
  "TheHive" \
  "raw logs" \
  "never" \
  "customer portal" \
  "no secrets" \
  "KB-036" \
  "KB-047" \
  "KB-049" \
  "deferred"
echo "OK: KB048 doc mentions Shuffle deployment plan and safety boundaries."

section "4. No obvious secrets in KB-048 docs"

DOC_SCAN_FILES=(
  docs/KB048_SHUFFLE_SOAR_DEPLOYMENT_PLAN.md
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
  fail "Possible secret material found in KB-048 documentation files"
fi
echo "OK: no obvious secret assignments in KB-048 docs."

section "5. Final verdict"

echo "======================================================================"
echo "KB-048 SHUFFLE SOAR DEPLOYMENT PLAN VALIDATION PASSED"
echo "======================================================================"
