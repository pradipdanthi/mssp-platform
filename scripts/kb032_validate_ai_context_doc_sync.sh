#!/usr/bin/env bash
# KB-032: Validate AI Context and Documentation Sync (docs only).
# Confirms context files are present, mention KB-031/032 safety rules,
# and that runtime/protected paths were not modified by this module.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-032: Validate AI Context Doc Sync"
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
    grep -q "$needle" "$file" || fail "$file missing required mention: $needle"
  done
}

section "1. Required documentation files exist"

REQUIRED=(
  "AGENTS.md"
  "CLAUDE.md"
  ".cursor/rules/mssp-control-plane.mdc"
  "CONTEXT.md"
  "docs/AI_PROMPT_LEDGER.md"
  "docs/KB032_AI_CONTEXT_DOC_SYNC.md"
  "scripts/kb032_validate_ai_context_doc_sync.sh"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-032 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-032 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. CONTEXT.md size must be substantial"

CONTEXT_SIZE="$(wc -c < CONTEXT.md | tr -d ' ')"
[ "$CONTEXT_SIZE" -gt 5000 ] || fail "CONTEXT.md size is ${CONTEXT_SIZE} bytes; expected > 5000"
echo "OK: CONTEXT.md size is ${CONTEXT_SIZE} bytes (> 5000)."

section "4. CONTEXT.md required mentions"

file_mentions CONTEXT.md \
  "KB-031" \
  "d27bdea" \
  "kb031-customer-report-detail-validated" \
  "customer report detail" \
  "no /admin" \
  "no .env" \
  "validation before commit"
echo "OK: CONTEXT.md mentions KB-031 pointers and safety rules."

section "5. AGENTS.md / CLAUDE.md / Cursor rule required mentions"

for f in AGENTS.md CLAUDE.md .cursor/rules/mssp-control-plane.mdc; do
  file_mentions "$f" \
    "KB-031" \
    "planning before implementation" \
    "no .env" \
    "no /admin" \
    "validation before commit"
  echo "OK: $f mentions KB-031 and workflow/safety rules."
done

section "6. AI_PROMPT_LEDGER.md required mentions"

file_mentions docs/AI_PROMPT_LEDGER.md \
  "KB-031" \
  "KB-032" \
  "kb031-customer-report-detail-validated"
echo "OK: ledger mentions KB-031, KB-032, and kb031 tag."

section "7. No obvious secrets in updated docs"

DOC_SCAN_FILES=(
  AGENTS.md
  CLAUDE.md
  CONTEXT.md
  docs/AI_PROMPT_LEDGER.md
  docs/KB032_AI_CONTEXT_DOC_SYNC.md
  .cursor/rules/mssp-control-plane.mdc
)

# Reject common secret assignment patterns / obvious credential material.
# Allow discussion of field *names* like password_hash in prose.
SECRET_HIT="$(grep -REn \
  -e 'password[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{6,}' \
  -e 'api_key[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{6,}' \
  -e 'token[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{8,}' \
  -e 'JWT_SECRET[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]+' \
  -e 'Bearer[[:space:]]+[A-Za-z0-9_-]{20,}' \
  "${DOC_SCAN_FILES[@]}" 2>/dev/null || true)"

if [ -n "$SECRET_HIT" ]; then
  echo "$SECRET_HIT" >&2
  fail "Possible secret material found in documentation files"
fi
echo "OK: no obvious password/token/api_key secret assignments in updated docs."

section "8. Final verdict"

echo "======================================================================"
echo "KB-032 AI CONTEXT DOC SYNC VALIDATION PASSED"
echo "======================================================================"
