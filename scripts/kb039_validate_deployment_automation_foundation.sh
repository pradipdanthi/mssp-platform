#!/usr/bin/env bash
# KB-039: Validate Deployment Automation Foundation (docs + Ansible scaffolding).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-039: Validate Deployment Automation Foundation"
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
  "docs/KB039_DEPLOYMENT_AUTOMATION_FOUNDATION.md"
  "scripts/kb039_validate_deployment_automation_foundation.sh"
  "ansible/README.md"
  "ansible/ansible.cfg"
  "ansible/inventory/hosts.yml"
  "ansible/group_vars/all.yml"
  "ansible/playbooks/bootstrap.yml"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-039 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-039 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB039 doc required mentions"

file_mentions docs/KB039_DEPLOYMENT_AUTOMATION_FOUNDATION.md \
  "Purpose" \
  "ansible" \
  "deployment automation" \
  "VM 100" \
  "VM 101" \
  "VM 111" \
  "KB-036" \
  "KB-037" \
  "KB-038" \
  "no secrets" \
  "customer portal" \
  "raw logs" \
  "never" \
  "Deferred" \
  "deferred"
echo "OK: KB039 doc mentions automation foundation, VMs, links, and safety."

section "4. Ansible inventory covers VM 100-111 placeholders"

file_mentions ansible/inventory/hosts.yml \
  "vm_id: 100" \
  "vm_id: 101" \
  "vm_id: 106" \
  "vm_id: 111" \
  "mssp-control" \
  "wazuh-stack" \
  "suricata-sensor"
echo "OK: inventory has VM 100-111 placeholder hosts."

section "5. Ansible scaffolding has no obvious secrets"

SCAN_FILES=(
  docs/KB039_DEPLOYMENT_AUTOMATION_FOUNDATION.md
  ansible/README.md
  ansible/ansible.cfg
  ansible/inventory/hosts.yml
  ansible/group_vars/all.yml
  ansible/playbooks/bootstrap.yml
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
  fail "Possible secret material found in KB-039 files"
fi
echo "OK: no obvious secret assignments in KB-039 scaffolding."

section "6. Bootstrap playbook is stub only"

file_mentions ansible/playbooks/bootstrap.yml \
  "stub" \
  "Deferred" \
  "no secrets"
echo "OK: bootstrap.yml is a deferred stub."

section "7. Final verdict"

echo "======================================================================"
echo "KB-039 DEPLOYMENT AUTOMATION FOUNDATION VALIDATION PASSED"
echo "======================================================================"
