#!/usr/bin/env bash
# KB-093 C / B2 — Packer disposable-VM pipeline validation
# Default: builder image + packer validate + ansible syntax (no long ISO build).
# Set KEVANTIC_B2_FULL=1 to also run Packer QEMU build after ISO is present.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/kevantic-appliance"
FAIL=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; FAIL=1; }

echo "=== KB-093 B2 Packer disposable VM pipeline validation ==="

need() { [[ -f "$1" ]] && pass "file ${1#"$ROOT"/}" || fail "missing ${1#"$ROOT"/}"; }

need "$APP/packer/ubuntu-lts.pkr.hcl"
need "$APP/packer/http/user-data"
need "$APP/packer/http/meta-data"
need "$APP/packer/scripts/00-minimize-bootstrap.sh"
need "$APP/packer/scripts/10-wait-cloud-init.sh"
need "$APP/packer/vars/b2-docker.pkrvars.hcl"
need "$APP/ansible/playbooks/b2-smoke.yml"
need "$APP/ci/Dockerfile.b2-builder"
need "$APP/scripts/b2_fetch_ubuntu_iso.sh"
need "$APP/scripts/b2_build_builder_image.sh"
need "$APP/scripts/b2_packer_validate.sh"
need "$APP/scripts/b2_packer_build.sh"
need "$APP/docs/B2_PACKER_DISPOSABLE_VM.md"

# Safety: must not apt-install TheHive (comments that forbid it are OK)
if grep -RniE 'apt-get[[:space:]]+install[^\n]*thehive|[[:space:]]+thehive([[:space:]]|$)' \
  "$APP/packer/http/user-data" 2>/dev/null; then
  fail "B2 autoinstall must not install TheHive"
elif grep -niE '^\s*-\s*thehive\s*$' "$APP/ansible/playbooks/b2-smoke.yml" 2>/dev/null; then
  fail "B2 smoke playbook must not list TheHive as a package"
else
  pass "no TheHive package install in B2 autoinstall/smoke playbook"
fi

# Production split still documented
if grep -qiE 'separate server|Appliance Management Plane' \
  "$ROOT/docs/KB093_KEVANTIC_HARDENED_ON_PREM_APPLIANCE_ARCHITECTURE.md"; then
  pass "KB-093 still documents separate Appliance Mgmt server"
else
  fail "missing separate server note"
fi

# Build tools present?
if ! command -v docker >/dev/null; then
  fail "docker required for B2 builder"
else
  pass "docker available"
fi

chmod +x "$APP"/scripts/b2_*.sh "$APP"/packer/scripts/*.sh

echo "--- building B2 builder image ---"
if "$APP/scripts/b2_build_builder_image.sh"; then
  pass "builder image build"
else
  fail "builder image build"
fi

echo "--- packer validate + ansible syntax ---"
if "$APP/scripts/b2_packer_validate.sh"; then
  pass "packer validate + ansible syntax"
else
  fail "packer validate + ansible syntax"
fi

# Prior B1 still green
if "$ROOT/scripts/kb093b_validate_kevantic_cli_b1.sh" >/tmp/kb093b-out.txt; then
  pass "B1 regression"
else
  fail "B1 regression"
  tail -20 /tmp/kb093b-out.txt || true
fi

if [[ "${KEVANTIC_B2_FULL:-0}" == "1" ]]; then
  echo "--- FULL Packer QEMU build (KEVANTIC_B2_FULL=1) ---"
  "$APP/scripts/b2_fetch_ubuntu_iso.sh"
  if "$APP/scripts/b2_packer_build.sh"; then
    pass "full packer qemu build"
  else
    fail "full packer qemu build"
  fi
else
  pass "skipped full ISO build (set KEVANTIC_B2_FULL=1 to enable)"
  if [[ -f "$APP/.cache/ubuntu-24.04.4-live-server-amd64.iso" ]]; then
    pass "Ubuntu ISO present in .cache (ready for full build)"
  else
    pass "Ubuntu ISO not yet in .cache (run b2_fetch_ubuntu_iso.sh before full build)"
  fi
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "KB-093 B2 PACKER DISPOSABLE VM PIPELINE VALIDATION FAILED"
  exit 1
fi
echo "KB-093 B2 PACKER DISPOSABLE VM PIPELINE VALIDATION PASSED"
