#!/usr/bin/env bash
# KB-049: Validate Wazuh to Shuffle to TheHive Workflow (docs only).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-049: Validate Wazuh to Shuffle to TheHive Workflow"
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
  "docs/KB049_WAZUH_SHUFFLE_THEHIVE_WORKFLOW.md"
  "scripts/kb049_validate_wazuh_shuffle_thehive_workflow.sh"
  "docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md"
  "docs/KB047_THEHIVE_DEPLOYMENT_PLAN.md"
  "docs/KB048_SHUFFLE_SOAR_DEPLOYMENT_PLAN.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" 2>/dev/null || fail "$p has working-tree changes but KB-049 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" 2>/dev/null || fail "$p has staged changes but KB-049 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB049 planning doc required mentions"

file_mentions docs/KB049_WAZUH_SHUFFLE_THEHIVE_WORKFLOW.md \
  "Wazuh" \
  "Shuffle" \
  "TheHive" \
  "VM 101" \
  "VM 102" \
  "VM 103" \
  "workflow" \
  "playbook" \
  "tenant_id" \
  "tenant isolation" \
  "dedup" \
  "raw logs" \
  "never" \
  "customer portal" \
  "no secrets" \
  "KB-036" \
  "KB-047" \
  "KB-048" \
  "KB-057" \
  "deferred"
echo "OK: KB049 doc mentions workflow architecture and safety boundaries."

section "4. No obvious secrets in KB-049 docs"

DOC_SCAN_FILES=(
  docs/KB049_WAZUH_SHUFFLE_THEHIVE_WORKFLOW.md
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
  fail "Possible secret material found in KB-049 documentation files"
fi
echo "OK: no obvious secret assignments in KB-049 docs."

section "5. Final verdict"

echo "======================================================================"
echo "KB-049 WAZUH SHUFFLE THEHIVE WORKFLOW VALIDATION PASSED"
echo "======================================================================"
