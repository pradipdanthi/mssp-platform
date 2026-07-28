#!/usr/bin/env bash
# KB-077: Validate Greenbone enterprise plan (deferred) + baseline posture docs.
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

check "KB-077 plan exists" test -f docs/KB077_GREENBONE_ENTERPRISE_READINESS_PLAN.md
check "plan defers procurement" file_has docs/KB077_GREENBONE_ENTERPRISE_READINESS_PLAN.md "Deferred"
check "plan names Community Edition" file_has docs/KB077_GREENBONE_ENTERPRISE_READINESS_PLAN.md "Community Edition"
check "plan names Enterprise Feed gap" file_has docs/KB077_GREENBONE_ENTERPRISE_READINESS_PLAN.md "Enterprise Feed"
check "plan references KB-078 free stack" file_has docs/KB077_GREENBONE_ENTERPRISE_READINESS_PLAN.md "KB-078"
check "plan has Phase E1 deploy" file_has docs/KB077_GREENBONE_ENTERPRISE_READINESS_PLAN.md "Phase E1"
check "plan forbids buy in this module" \
  file_has docs/KB077_GREENBONE_ENTERPRISE_READINESS_PLAN.md "Buy Enterprise feed/appliance in this module"
check "CONTEXT production posture" file_has CONTEXT.md "Production posture"
check "CONTEXT enterprise-ready mandate" file_has CONTEXT.md "enterprise-ready"
check "CONTEXT Nuclei free stack" file_has CONTEXT.md "Nuclei"
check "AGENTS enterprise posture section" file_has AGENTS.md "Enterprise readiness posture"
check "CLAUDE enterprise posture" file_has CLAUDE.md "enterprise-ready"
check "Cursor rule enterprise posture" \
  file_has .cursor/rules/mssp-control-plane.mdc "enterprise-ready"

echo "KB-077 checks: pass=$pass fail=$fail"
test "$fail" -eq 0
