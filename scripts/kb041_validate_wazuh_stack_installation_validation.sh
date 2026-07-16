#!/usr/bin/env bash
# KB-041: Validate Wazuh Stack Installation and Validation (stub playbook).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-041: Validate Wazuh Stack Installation and Validation"
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

section "1. Required files exist"

REQUIRED=(
  "docs/KB041_WAZUH_STACK_INSTALLATION_VALIDATION.md"
  "scripts/kb041_validate_wazuh_stack_installation_validation.sh"
  "ansible/playbooks/wazuh-stack-install.yml"
  "docs/KB040_WAZUH_STACK_VM_DEPLOYMENT_PLAN.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-041 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-041 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB041 doc required mentions"

file_mentions docs/KB041_WAZUH_STACK_INSTALLATION_VALIDATION.md \
  "Purpose" \
  "VM 101" \
  "wazuh-stack-install" \
  "KB-036" \
  "KB-037" \
  "KB-038" \
  "no secrets" \
  "customer portal" \
  "raw" \
  "never" \
  "NOT" \
  "live" \
  "Deferred" \
  "deferred"
echo "OK: KB041 doc mentions install plan, links, and deferred execution."

section "4. Playbook stub required mentions"

file_mentions ansible/playbooks/wazuh-stack-install.yml \
  "stub" \
  "VM 101" \
  "wazuh_stack" \
  "Deferred" \
  "no secrets" \
  "customer"
echo "OK: wazuh-stack-install.yml is a deferred stub."

section "5. No obvious secrets in KB-041 files"

SCAN_FILES=(
  docs/KB041_WAZUH_STACK_INSTALLATION_VALIDATION.md
  ansible/playbooks/wazuh-stack-install.yml
)

SECRET_HIT="$(grep -REn \
  -e 'password[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{6,}' \
  -e 'api_key[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{6,}' \
  -e 'token[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{8,}' \
  -e 'JWT_SECRET[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]+' \
  -e 'Bearer[[:space:]]+[A-Za-z0-9_-]{20,}' \
  "${SCAN_FILES[@]}" 2>/dev/null || true)"

if [ -n "$SECRET_HIT" ]; then
  echo "$SECRET_HIT" >&2
  fail "Possible secret material found in KB-041 files"
fi
echo "OK: no obvious secret assignments in KB-041 files."

section "6. Final verdict"

echo "======================================================================"
echo "KB-041 WAZUH STACK INSTALLATION VALIDATION PASSED"
echo "======================================================================"
