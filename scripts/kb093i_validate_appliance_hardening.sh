#!/usr/bin/env bash
# KB-093I / Track-2 — appliance hardening roles must be real (not scaffold).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/kevantic-appliance"
FAIL=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; FAIL=1; }

echo "=== Appliance Track-2 hardening validation ==="

for role in harden_cis auditd container_runtime apparmor_profiles; do
  f="$APP/ansible/roles/$role/tasks/main.yml"
  [[ -f "$f" ]] || { fail "missing $role tasks"; continue; }
  if grep -q 'scaffold-only' "$f"; then
    fail "role $role still scaffold-only"
  else
    pass "role $role implemented (not scaffold)"
  fi
done

# CIS artifacts
[[ -f "$APP/hardening/cis/exceptions.yml" ]] || fail "missing cis exceptions"
grep -q 'exceptions:' "$APP/hardening/cis/exceptions.yml" && pass "CIS exceptions register present" || fail "CIS exceptions empty/malformed"
grep -q '99-kevantic-cis.conf' "$APP/ansible/roles/harden_cis/tasks/main.yml" && pass "harden_cis writes sysctl drop-in" || fail "harden_cis sysctl missing"

# auditd
[[ -f "$APP/hardening/auditd/kevantic.rules" ]] || fail "missing auditd rules"
grep -q 'kevantic_secrets' "$APP/hardening/auditd/kevantic.rules" && pass "auditd watches secrets" || fail "auditd secrets watch missing"
grep -q 'kevantic.rules' "$APP/ansible/roles/auditd/tasks/main.yml" && pass "auditd role deploys rules" || fail "auditd deploy missing"

# container_runtime
grep -q 'podman' "$APP/ansible/roles/container_runtime/tasks/main.yml" && pass "container_runtime installs podman" || fail "podman missing"
grep -q 'offline' "$APP/ansible/roles/container_runtime/tasks/main.yml" && pass "container_runtime prefers offline pool" || fail "offline pool missing"

# apparmor
[[ -f "$APP/hardening/apparmor/usr.bin.kevantic-cli" ]] || fail "missing kevantic-cli AppArmor profile"
grep -q 'apparmor_parser' "$APP/ansible/roles/apparmor_profiles/tasks/main.yml" && pass "apparmor loads profiles" || fail "apparmor_parser missing"

# Wired into install provision
for role in harden_cis auditd container_runtime apparmor_profiles; do
  grep -q "$role" "$APP/ansible/playbooks/install-provision.yml" && pass "install-provision includes $role" || fail "install-provision missing $role"
done

# Ansible syntax check when available
if command -v ansible-playbook >/dev/null 2>&1; then
  if ansible-playbook --syntax-check "$APP/ansible/playbooks/install-provision.yml" -i localhost, >/tmp/kb093i-syntax.txt 2>&1; then
    pass "ansible-playbook syntax-check install-provision"
  else
    fail "ansible syntax-check failed (see /tmp/kb093i-syntax.txt)"
    tail -20 /tmp/kb093i-syntax.txt || true
  fi
else
  echo "WARN: ansible-playbook not installed on this host — skipped syntax-check"
fi

# No scaffold-only left in Track-2 roles (double-check)
if grep -R 'scaffold-only' "$APP/ansible/roles/harden_cis" "$APP/ansible/roles/auditd" \
  "$APP/ansible/roles/container_runtime" "$APP/ansible/roles/apparmor_profiles" >/dev/null 2>&1; then
  fail "scaffold-only string still present under Track-2 roles"
else
  pass "no scaffold-only markers in Track-2 roles"
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "APPLIANCE_TRACK2_HARDENING_VALIDATE_FAILED"
  exit 1
fi
echo "APPLIANCE_TRACK2_HARDENING_VALIDATE_OK"
