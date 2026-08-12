#!/usr/bin/env bash
# Validate customer portal entitlement-gated navigation + route guards.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; exit 1; }

test -f frontend-customer/src/config/navEntitlements.ts || fail "navEntitlements.ts missing"
test -f frontend-customer/src/config/EntitlementsContext.tsx || fail "EntitlementsContext.tsx missing"
test -f frontend-customer/src/components/EntitlementGate.tsx || fail "EntitlementGate.tsx missing"

grep -q 'buildCustomerNavItems' frontend-customer/src/components/Layout.tsx \
  || fail "Layout must build nav from entitlements"
grep -q 'EntitlementGate' frontend-customer/src/App.tsx \
  || fail "App must wrap add-on routes with EntitlementGate"
grep -q 'EntitlementsProvider' frontend-customer/src/main.tsx \
  || fail "main must provide EntitlementsProvider"
grep -q 'entitlementKeyForPath' frontend-customer/src/components/GlobalSearch.tsx \
  || fail "GlobalSearch must filter by entitlements"

# Static route coverage
for key in vulnerability_management continuous_compliance external_attack_surface \
  cloud_identity_protection network_detection threat_intelligence threatlens endpoint_forensics; do
  grep -q "require=\"$key\"" frontend-customer/src/App.tsx \
    || fail "App missing EntitlementGate require=$key"
done

# Core always-visible items still present in config
for label in Dashboard Alerts Incidents Assets "Service Portfolio"; do
  grep -q "$label" frontend-customer/src/config/navEntitlements.ts \
    || fail "CORE_NAV missing $label"
done

pass "Customer entitlement-gated nav + route guards present"
echo "RESULT: PASSED"
