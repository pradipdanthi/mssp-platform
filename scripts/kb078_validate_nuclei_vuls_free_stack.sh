#!/usr/bin/env bash
# KB-078: Validate Nuclei + Vuls free stack docs, automation, and live install on VM 109.
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"
pass=0
fail=0
check() {
  local name="$1"
  shift
  if "$@"; then
    echo "PASS: $name"
    pass=$((pass + 1))
  else
    echo "FAIL: $name"
    fail=$((fail + 1))
  fi
}
file_has() { grep -qE "$2" "$1"; }

echo "======================================================================"
echo "KB-078: Validate Nuclei + Vuls Free Stack (VM 109)"
echo "======================================================================"

check "KB-078 doc exists" test -f docs/KB078_NUCLEI_VULS_FREE_STACK.md
check "doc names Nuclei" file_has docs/KB078_NUCLEI_VULS_FREE_STACK.md "Nuclei"
check "doc names Vuls" file_has docs/KB078_NUCLEI_VULS_FREE_STACK.md "Vuls"
check "doc honest coverage vs Greenbone" file_has docs/KB078_NUCLEI_VULS_FREE_STACK.md "Honest coverage"
check "doc targets VM 109" file_has docs/KB078_NUCLEI_VULS_FREE_STACK.md "VM 109"
check "doc forbids control-plane install" file_has docs/KB078_NUCLEI_VULS_FREE_STACK.md "must \*\*not\*\* host"
check "doc uses secadmin not root SSH" file_has docs/KB078_NUCLEI_VULS_FREE_STACK.md "Root SSH login is not used"
check "doc defers Enterprise spend" file_has docs/KB078_NUCLEI_VULS_FREE_STACK.md "Deferred"

check "playbook exists" test -f ansible/playbooks/vuln-free-stack.yml
check "role defaults exist" test -f ansible/roles/vuln_free_stack/defaults/main.yml
check "role tasks exist" test -f ansible/roles/vuln_free_stack/tasks/main.yml
check "install script exists" test -f scripts/kb078_install_vuln_free_stack.sh
check "install script executable" test -x scripts/kb078_install_vuln_free_stack.sh

check "safe default is preflight" \
  file_has ansible/roles/vuln_free_stack/defaults/main.yml 'vuln_free_execution_mode: "preflight"'
check "live install gated" \
  file_has ansible/roles/vuln_free_stack/defaults/main.yml "vuln_free_live_install_approved: false"
check "role defaults install on /opt/mssp-vuln-free" \
  file_has ansible/roles/vuln_free_stack/defaults/main.yml "/opt/mssp-vuln-free"
check "role asserts VM 109" \
  grep -Fq '(vm_id | int) == 109' ansible/roles/vuln_free_stack/tasks/main.yml
check "inventory has vuln_free_stack" \
  file_has ansible/inventory/hosts.yml "vuln_free_stack:"
check "inventory targets 192.168.0.219" \
  file_has ansible/inventory/hosts.yml "ansible_host: 192.168.0.219"
check "inventory uses id_ed25519_greenbone key" \
  file_has ansible/inventory/hosts.yml "id_ed25519_greenbone"
check "inventory deployment_role vuln_free_stack" \
  file_has ansible/inventory/hosts.yml "deployment_role: vuln_free_stack"

check "schema allows nuclei source" \
  file_has backend-api/app/schemas/vulnerabilities.py '"nuclei"'
check "schema allows vuls source" \
  file_has backend-api/app/schemas/vulnerabilities.py '"vuls"'

check "CONTEXT mentions Nuclei" file_has CONTEXT.md "Nuclei"
check "CONTEXT places stack on VM 109" file_has CONTEXT.md "Nuclei \+ Vuls"
check "control plane has no local vuln-free tree" \
  bash -c 'test ! -e /opt/mssp-control/runtime/vuln-free'

# Live install on VM 109 via Host "greenbone" SSH config
ssh_ok() {
  ssh -o BatchMode=yes -o ConnectTimeout=10 greenbone "$@"
}

if ssh_ok 'echo ok' >/dev/null 2>&1; then
  check "SSH to greenbone (secadmin) works" true
  check "live Nuclei on VM 109" \
    ssh_ok 'sudo test -x /opt/mssp-vuln-free/bin/nuclei && sudo /opt/mssp-vuln-free/bin/nuclei -version'
  check "live Vuls image on VM 109" \
    ssh_ok 'sudo docker image inspect vuls/vuls:latest >/dev/null'
  check "install marker on VM 109" \
    ssh_ok 'sudo test -f /var/lib/mssp/vuln-free/installed'
else
  check "SSH to greenbone (secadmin) works" false
  check "live Nuclei on VM 109" false
  check "live Vuls image on VM 109" false
  check "install marker on VM 109" false
fi

echo
echo "KB-078 checks: pass=$pass fail=$fail"
test "$fail" -eq 0
echo "======================================================================"
echo "KB-078 NUCLEI + VULS FREE STACK VALIDATION PASSED"
echo "======================================================================"
