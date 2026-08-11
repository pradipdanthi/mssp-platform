#!/usr/bin/env bash
# KB-093 — Validate Kevantic Hardened On-Prem Appliance architecture scaffold (docs + layout).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; FAIL=1; }

need_file() {
  local f="$1"
  if [[ -f "$ROOT/$f" ]]; then pass "file $f"
  else fail "missing file $f"
  fi
}

need_dir() {
  local d="$1"
  if [[ -d "$ROOT/$d" ]]; then pass "dir $d"
  else fail "missing dir $d"
  fi
}

echo "=== KB-093 Kevantic appliance architecture validation ==="

need_file "docs/KB093_KEVANTIC_HARDENED_ON_PREM_APPLIANCE_ARCHITECTURE.md"
need_file "kevantic-appliance/README.md"
need_file "kevantic-appliance/VERSION"
need_file "kevantic-appliance/docs/REPO_LAYOUT.md"
need_file "kevantic-appliance/docs/KEVANTIC_CLI_SPEC.md"
need_file "kevantic-appliance/docs/PACKAGE_PURGE_LIST.md"
need_file "kevantic-appliance/docs/SERVICE_MATRIX.md"
need_file "kevantic-appliance/packer/ubuntu-lts.pkr.hcl"
need_file "kevantic-appliance/packer/http/user-data"
need_file "kevantic-appliance/ansible/playbooks/site.yml"
need_file "kevantic-appliance/channel/schemas/envelope.v1.json"
need_file "kevantic-appliance/channel/schemas/license-push.v1.json"
need_file "kevantic-appliance/hardening/nftables/kevantic-appliance.nft"
need_file "kevantic-appliance/configs/systemd/kevantic-channeld.service"
need_file "kevantic-appliance/cli/kevantic-cli/README.md"

for role in minimize harden_cis firewall_nftables apparmor_profiles auditd container_runtime \
  kevantic_runtime channel_agent license_enforcer service_manager wazuh_local ota_staging; do
  need_file "kevantic-appliance/ansible/roles/${role}/tasks/main.yml"
done

for svc in 01-log-event 02-ir-worker 03-automation 04-vmaas 05-compliance \
  06-ndr 07-threat-intel 08-forensics 09-easm 10-itdr; do
  need_file "kevantic-appliance/services/${svc}/service.yaml"
  need_file "kevantic-appliance/services/${svc}/README.md"
done

# Content gates — architecture must state key decisions
DOC="$ROOT/docs/KB093_KEVANTIC_HARDENED_ON_PREM_APPLIANCE_ARCHITECTURE.md"
for needle in "outbound" "mTLS" "wazuh-agent" "kevantic-cli" "soc.kevantic.com" "LUKS" "entitlement" "WPK" "svc-01" \
  "TheHive" "BOOTSTRAP" "LOCKED" "single" "network lock" "cloud_appliance"; do
  if grep -Fq -- "$needle" "$DOC"; then pass "KB-093 mentions $needle"
  else fail "KB-093 missing required mention: $needle"
  fi
done

# Explicit: TheHive must be excluded from appliance (not installed)
if grep -Fq "No TheHive" "$DOC" || grep -Fq "never on appliance" "$DOC" || grep -Fq "NOT on the appliance" "$DOC"; then
  pass "KB-093 excludes TheHive from appliance"
else
  fail "KB-093 must explicitly exclude TheHive from appliance"
fi

CLI="$ROOT/kevantic-appliance/docs/KEVANTIC_CLI_SPEC.md"
for needle in "enable-service" "offboard" "wipe" "license apply" "setup" "--json" "bootstrap update" "network lock"; do
  if grep -Fq -- "$needle" "$CLI"; then pass "CLI spec mentions $needle"
  else fail "CLI spec missing: $needle"
  fi
done

# Safety: no private key PEM material in scaffold
if grep -R --include='*.pem' --include='*.key' -l 'BEGIN.*PRIVATE KEY' "$ROOT/kevantic-appliance" 2>/dev/null | grep -q .; then
  fail "private key material found under kevantic-appliance/"
else
  pass "no private key PEM material in kevantic-appliance/"
fi

# Must not claim control-plane runtime edits in this KB scope check (files untouched expectation is soft)
pass "scaffold checks complete"

if [[ "$FAIL" -ne 0 ]]; then
  echo "KB-093 KEVANTIC HARDENED ON-PREM APPLIANCE ARCHITECTURE VALIDATION FAILED"
  exit 1
fi

echo "KB-093 KEVANTIC HARDENED ON-PREM APPLIANCE ARCHITECTURE VALIDATION PASSED"
