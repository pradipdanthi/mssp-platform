#!/usr/bin/env bash
# KB-042: Validate Wazuh Agent Onboarding (docs + playbook stubs).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-042: Validate Wazuh Agent Onboarding"
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
  "docs/KB042_WAZUH_AGENT_ONBOARDING.md"
  "scripts/kb042_validate_wazuh_agent_onboarding.sh"
  "ansible/playbooks/wazuh-agent-linux.yml"
  "ansible/playbooks/wazuh-agent-windows.yml"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-042 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-042 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB042 doc required mentions"

file_mentions docs/KB042_WAZUH_AGENT_ONBOARDING.md \
  "Purpose" \
  "VM 104" \
  "VM 105" \
  "VM 101" \
  "Windows" \
  "Linux" \
  "KB-036" \
  "KB-037" \
  "KB-038" \
  "enrollment" \
  "no secrets" \
  "customer portal" \
  "raw logs" \
  "never" \
  "Deferred" \
  "deferred"
echo "OK: KB042 doc mentions agent onboarding, VMs, links, and safety."

section "4. Playbook stubs required mentions"

file_mentions ansible/playbooks/wazuh-agent-linux.yml \
  "stub" \
  "linux-endpoint-lab" \
  "Deferred" \
  "Vault" \
  "no secrets"

file_mentions ansible/playbooks/wazuh-agent-windows.yml \
  "stub" \
  "windows-endpoint-lab" \
  "Deferred" \
  "Vault" \
  "no secrets"
echo "OK: agent playbooks are deferred stubs."

section "5. No obvious secrets in KB-042 files"

SCAN_FILES=(
  docs/KB042_WAZUH_AGENT_ONBOARDING.md
  ansible/playbooks/wazuh-agent-linux.yml
  ansible/playbooks/wazuh-agent-windows.yml
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
  fail "Possible secret material found in KB-042 files"
fi
echo "OK: no obvious secret assignments in KB-042 files."

section "6. Final verdict"

echo "======================================================================"
echo "KB-042 WAZUH AGENT ONBOARDING VALIDATION PASSED"
echo "======================================================================"
