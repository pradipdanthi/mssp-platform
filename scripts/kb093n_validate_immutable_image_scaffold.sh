#!/usr/bin/env bash
# KB-093N — validate immutable appliance scaffold (strategy + mkosi layout)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/kevantic-appliance"
PASS=0
fail() { echo "FAIL: $*"; exit 1; }
ok() { echo "PASS: $*"; PASS=$((PASS + 1)); }

[[ -f "$ROOT/docs/KB093N_IMMUTABLE_APPLIANCE_IMAGE_STRATEGY.md" ]] \
  || fail "missing KB093N strategy doc"
grep -q 'mkosi' "$ROOT/docs/KB093N_IMMUTABLE_APPLIANCE_IMAGE_STRATEGY.md" \
  || fail "KB093N must name mkosi toolchain"
grep -q 'dm-verity\|A/B\|UKI' "$ROOT/docs/KB093N_IMMUTABLE_APPLIANCE_IMAGE_STRATEGY.md" \
  || fail "KB093N must cover verity/UKI/A/B"
ok "KB093N strategy doc present"

[[ -f "$APP/mkosi/mkosi.conf" ]] || fail "missing mkosi/mkosi.conf"
[[ -x "$APP/mkosi/build.sh" ]] || fail "mkosi/build.sh not executable"
[[ -f "$APP/iso/DEPRECATED_REMASTER.txt" ]] || fail "remaster not marked deprecated"
ok "mkosi scaffold + remaster deprecation marker"

# Remaster must not be advertised as primary in README
grep -q 'KB-093N\|mkosi' "$APP/README.md" || fail "README must point at KB-093N/mkosi"
ok "README points at immutable strategy"

# Reusable assets still present for bake-in
[[ -d "$APP/cli/kevantic-cli" ]] || fail "missing kevantic-cli tree"
[[ -d "$APP/channel" ]] || fail "missing channel/"
[[ -d "$APP/hardening/nftables" ]] || fail "missing nftables hardening"
ok "reusable cli/channel/hardening retained"

if command -v mkosi >/dev/null 2>&1; then
  ok "mkosi binary available on host"
else
  echo "WARN: mkosi not installed yet — install before N1 image build"
fi

echo
echo "KB093N_VALIDATE_OK checks_passed=$PASS"
echo "Next: sudo apt-get install -y mkosi systemd-container uidmap qemu-utils"
echo "Then: $APP/mkosi/build.sh"
