#!/usr/bin/env bash
# KB-055: Validate DFIR Evidence Safety and Case Workflow (docs only).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-055: Validate DFIR Evidence Safety and Case Workflow"
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
  "docs/KB055_DFIR_EVIDENCE_SAFETY_CASE_WORKFLOW.md"
  "scripts/kb055_validate_dfir_evidence_safety_case_workflow.sh"
  "docs/KB054_VELOCIRAPTOR_DFIR_DEPLOYMENT_PLAN.md"
  "docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" 2>/dev/null || fail "$p has working-tree changes but KB-055 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" 2>/dev/null || fail "$p has staged changes but KB-055 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB055 planning doc required mentions"

file_mentions docs/KB055_DFIR_EVIDENCE_SAFETY_CASE_WORKFLOW.md \
  "Purpose" \
  "VM 110" \
  "Velociraptor" \
  "tenant_id" \
  "tenant isolation" \
  "no secrets" \
  "customer portal" \
  "Never" \
  "KB-036" \
  "KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP" \
  "KB-054" \
  "chain of custody" \
  "TheHive" \
  "evidence"
echo "OK: KB055 doc mentions evidence safety, case workflow, tenant isolation, customer safety, and KB-036."

section "4. KB055 builds on KB-054"

file_mentions docs/KB055_DFIR_EVIDENCE_SAFETY_CASE_WORKFLOW.md \
  "KB054_VELOCIRAPTOR_DFIR_DEPLOYMENT_PLAN"
echo "OK: KB055 references KB-054 Velociraptor plan."

section "5. No obvious secrets in KB-055 docs"

DOC_SCAN_FILES=(
  docs/KB055_DFIR_EVIDENCE_SAFETY_CASE_WORKFLOW.md
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
  fail "Possible secret material found in KB-055 documentation files"
fi
echo "OK: no obvious secret assignments in KB-055 docs."

section "6. Final verdict"

echo "======================================================================"
echo "KB-055 DFIR EVIDENCE SAFETY CASE WORKFLOW VALIDATION PASSED"
echo "======================================================================"
