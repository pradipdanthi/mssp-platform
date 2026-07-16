#!/usr/bin/env bash
# KB-051: Validate Threat Intel Enrichment Workflow (docs only).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-051: Validate Threat Intel Enrichment Workflow"
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
  "docs/KB051_THREAT_INTEL_ENRICHMENT_WORKFLOW.md"
  "scripts/kb051_validate_threat_intel_enrichment_workflow.sh"
  "docs/KB050_MISP_THREAT_INTEL_DEPLOYMENT_PLAN.md"
  "docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" 2>/dev/null || fail "$p has working-tree changes but KB-051 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" 2>/dev/null || fail "$p has staged changes but KB-051 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB051 planning doc required mentions"

file_mentions docs/KB051_THREAT_INTEL_ENRICHMENT_WORKFLOW.md \
  "Purpose" \
  "VM 108" \
  "MISP" \
  "tenant_id" \
  "tenant isolation" \
  "no secrets" \
  "customer portal" \
  "Never" \
  "KB-036" \
  "KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP" \
  "KB-050" \
  "enrichment" \
  "plain-English"
echo "OK: KB051 doc mentions enrichment workflow, tenant isolation, customer safety, and KB-036."

section "4. KB051 builds on KB-050"

file_mentions docs/KB051_THREAT_INTEL_ENRICHMENT_WORKFLOW.md \
  "KB050_MISP_THREAT_INTEL_DEPLOYMENT_PLAN"
echo "OK: KB051 references KB-050 deployment plan."

section "5. No obvious secrets in KB-051 docs"

DOC_SCAN_FILES=(
  docs/KB051_THREAT_INTEL_ENRICHMENT_WORKFLOW.md
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
  fail "Possible secret material found in KB-051 documentation files"
fi
echo "OK: no obvious secret assignments in KB-051 docs."

section "6. Final verdict"

echo "======================================================================"
echo "KB-051 THREAT INTEL ENRICHMENT WORKFLOW VALIDATION PASSED"
echo "======================================================================"
