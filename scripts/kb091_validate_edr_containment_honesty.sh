#!/usr/bin/env bash
# KB-091: Containment honesty + AR packaging/preflight checks (not live ping proof).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; exit 1; }

grep -q 'Never guess' backend-api/app/services/wazuh_client.py \
  || fail "get_agent_os must fail closed / never guess"
grep -q 'OS is unknown' backend-api/app/services/edr_actions.py \
  || fail "_resolve_ar_command must refuse unknown OS"
grep -q 'NOT prevent execution' backend-api/app/services/edr_actions.py \
  || fail "BLOCK_HASH must disclose lack of enforcement"
grep -q 'firewall isolation not proven' backend-api/app/services/edr_actions.py \
  || fail "verify_isolation_state must not claim isolation proven"
grep -q 'Dispatched' frontend-admin/src/api/edr.ts \
  || fail "admin EDR badges must use Dispatched for unverified actions"
grep -q 'KILL_PROCESS' frontend-admin/src/api/edr.ts \
  || fail "admin badges must special-case KILL_PROCESS"
grep -q 'Dispatched' frontend-customer/src/api/edr.ts \
  || fail "customer EDR badges must use Dispatched"
grep -q 'blockoutbound' deploy/wazuh-active-response/windows/mssp-isolate-host.ps1 \
  || fail "Windows isolate must use blockoutbound policy"
test -f docs/KB091_ENTERPRISE_CONTAINMENT_HONESTY_GAPS.md \
  || fail "gap register missing"

# Dual-tree drift check (deploy is SoT)
./scripts/kb091_sync_windows_edr_ar_pack.sh >/dev/null
diff -q \
  deploy/wazuh-active-response/windows/mssp-isolate-host.ps1 \
  backend-api/app/endpoint_configs/windows-edr-ar/mssp-isolate-host.ps1 \
  >/dev/null || fail "AR pack drift after sync"

# Optional live Manager command registration check
KEY="${WAZUH_SSH_KEY:-/home/secadmin/.ssh/id_ed25519_wazuh_stack}"
HOST="${WAZUH_MANAGER_HOST:-192.168.0.211}"
if [[ -f "$KEY" ]]; then
  if ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new \
    "secadmin@${HOST}" 'sudo grep -q "<name>mssp-isolate-host.cmd</name>" /var/ossec/etc/ossec.conf'; then
    pass "Manager has mssp-isolate-host.cmd registered"
  else
    fail "Manager missing mssp-isolate-host.cmd — run scripts/kb090_register_windows_edr_ar_commands.sh"
  fi
else
  pass "skipped Manager SSH preflight (no key)"
fi

pass "kb091 containment honesty checks"
echo "NOTE: This does NOT prove gateway ping fails on a Windows host."
echo "      Wave 1 live proof still required (see docs/KB091_ENTERPRISE_CONTAINMENT_HONESTY_GAPS.md)."
