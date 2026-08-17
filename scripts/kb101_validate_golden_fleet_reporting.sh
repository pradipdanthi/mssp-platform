#!/usr/bin/env bash
# KB-101: Golden VM 199 must bake fleet-reporting heartbeat (inventory + metrics + image-release).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/kevantic-appliance"
FAIL=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; FAIL=1; }

echo "=== KB-101 golden appliance fleet reporting ==="

need() { [[ -f "$1" ]] && pass "file ${1#"$ROOT"/}" || fail "missing ${1#"$ROOT"/}"; }

need "$APP/cli/kevantic-cli/kevantic_cli/register_ops.py"
need "$APP/cli/kevantic-cli/kevantic_cli/state.py"
need "$APP/configs/image-release.json"
need "$APP/configs/systemd/kevantic-heartbeat.service"
need "$APP/configs/systemd/junexis-heartbeat.service"
need "$APP/configs/systemd/junexis-heartbeat.timer"
need "$APP/scripts/bake_golden_vm199_fleet_reporting.sh"
need "$APP/scripts/upgrade_appliance_fleet_reporting.sh"
need "$APP/scripts/upgrade_appliance_heartbeat_inventory.sh"

grep -q '_collect_resource_metrics' "$APP/cli/kevantic-cli/kevantic_cli/register_ops.py" \
  && pass "CLI collects CPU/mem/disk" \
  || fail "register_ops.py missing _collect_resource_metrics"

grep -q 'apply_entitlements' "$APP/cli/kevantic-cli/kevantic_cli/register_ops.py" \
  && pass "CLI applies entitlement jobs" \
  || fail "register_ops.py missing apply_entitlements job handler"

grep -q '_authenticate_local_wazuh' "$APP/cli/kevantic-cli/kevantic_cli/register_ops.py" \
  && pass "CLI authenticates to local Manager without operator env" \
  || fail "register_ops.py missing local Wazuh API auth helper"

grep -q '_ensure_local_edr_ar_commands' "$APP/cli/kevantic-cli/kevantic_cli/register_ops.py" \
  && pass "CLI registers isolate AR commands on local Manager" \
  || fail "register_ops.py missing EDR AR command ensure"

grep -q '_publish_windows_edr_ar_shared' "$APP/cli/kevantic-cli/kevantic_cli/register_ops.py" \
  && pass "CLI publishes Windows isolate scripts to Manager shared groups" \
  || fail "register_ops.py missing Windows EDR shared publish"

grep -q 'Watch-MsspQuarantine.ps1' "$APP/scripts/bake_golden_vm199_fleet_reporting.sh" \
  && pass "golden bake ships Windows isolate watchdog" \
  || fail "bake script missing Watch-MsspQuarantine.ps1"

grep -q 'mssp-kill-process.cmd' "$APP/scripts/bake_golden_vm199_fleet_reporting.sh" \
  && pass "golden bake ships full Windows EDR AR pack" \
  || fail "bake script missing Windows kill/block-hash AR files"

grep -q '_cli_submodule' "$APP/cli/kevantic-cli/kevantic_cli/register_ops.py" \
  && pass "CLI loads branded junexis/kevantic modules without hard fail" \
  || fail "register_ops.py missing branded CLI import helper"

grep -q 'apply_entitlements' "$APP/scripts/bake_golden_vm199_fleet_reporting.sh" \
  && pass "golden bake verifies apply_entitlements" \
  || fail "bake script missing apply_entitlements verify"

grep -q '_read_enabled_services' "$APP/cli/kevantic-cli/kevantic_cli/register_ops.py" \
  && pass "CLI reports enabled_services" \
  || fail "register_ops.py missing _read_enabled_services"

grep -q 'image-release.json' "$APP/cli/kevantic-cli/kevantic_cli/register_ops.py" \
  && pass "CLI reads image-release.json" \
  || fail "register_ops.py missing image-release.json read"

grep -F 'ExecStart=/usr/bin/python3 -m kevantic_cli heartbeat' \
  "$APP/configs/systemd/kevantic-heartbeat.service" \
  && pass "kevantic heartbeat uses python -m" \
  || fail "kevantic-heartbeat.service still uses bash wrapper"

grep -F 'ExecStart=/usr/bin/python3 -m junexis_cli heartbeat' \
  "$APP/configs/systemd/junexis-heartbeat.service" \
  && pass "junexis heartbeat uses python -m" \
  || fail "junexis-heartbeat.service still uses bash wrapper"

grep -q 'image-release.json' "$APP/ansible/roles/kevantic_runtime/tasks/main.yml" \
  && pass "ansible runtime installs image-release.json" \
  || fail "kevantic_runtime missing image-release.json"

grep -q 'junexis-heartbeat.service' "$APP/ansible/roles/kevantic_runtime/tasks/main.yml" \
  && pass "ansible runtime installs junexis heartbeat unit" \
  || fail "kevantic_runtime missing junexis-heartbeat.service"

grep -q 'python3 -m kevantic_cli heartbeat' "$APP/ansible/playbooks/install-provision.yml" \
  && pass "install-provision asserts python -m heartbeat" \
  || fail "install-provision missing heartbeat assert"

grep -q 'image-release.json' "$APP/ansible/playbooks/install-provision.yml" \
  && pass "install-provision asserts image-release.json" \
  || fail "install-provision missing image-release assert"

grep -q 'python3 -m kevantic_cli heartbeat' "$APP/mkosi/mkosi.postinst" \
  && pass "mkosi postinst checks heartbeat unit" \
  || fail "mkosi.postinst missing heartbeat check"

if grep -q 'seeded by upgrade_appliance_fleet_reporting' "$APP/scripts/bake_golden_vm199_fleet_reporting.sh"; then
  fail "golden bake script must not seed lab entitlements"
else
  pass "golden bake script does not seed lab entitlements"
fi

grep -q 'Do not seed entitlements' "$APP/scripts/bake_golden_vm199_fleet_reporting.sh" \
  && pass "golden bake documents no entitlement seed" \
  || fail "bake script missing no-seed guard"

if [[ "$FAIL" -ne 0 ]]; then
  echo
  echo "KB-101 VALIDATION FAILED"
  exit 1
fi

echo
echo "======================================================================"
echo "KB-101 VALIDATION PASSED"
echo "======================================================================"
