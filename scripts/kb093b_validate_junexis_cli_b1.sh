#!/usr/bin/env bash
# KB-093 B1 — junexis-cli + nft profiles + minimize role smoke (no root apt/nft required)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI_DIR="$ROOT/junexis-appliance/cli/junexis-cli"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export JUNEXIS_STATE_DIR="$TMP/state"
export JUNEXIS_CONFIG_DIR="$TMP/config"
export PYTHONPATH="$CLI_DIR${PYTHONPATH:+:$PYTHONPATH}"

FAIL=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; FAIL=1; }

echo "=== KB-093 B1 junexis-cli / bootstrap-lock validation ==="

need() {
  [[ -f "$1" ]] && pass "file ${1#"$ROOT"/}" || fail "missing ${1#"$ROOT"/}"
}

need "$ROOT/junexis-appliance/hardening/nftables/bootstrap.nft"
need "$ROOT/junexis-appliance/hardening/nftables/locked.nft"
need "$ROOT/junexis-appliance/ansible/roles/minimize/tasks/main.yml"
need "$ROOT/junexis-appliance/cli/junexis-cli/junexis_cli/cli.py"
need "$ROOT/docs/KB093_JUNEXIS_HARDENED_ON_PREM_APPLIANCE_ARCHITECTURE.md"

if grep -Fq "Separate server" "$ROOT/docs/KB093_JUNEXIS_HARDENED_ON_PREM_APPLIANCE_ARCHITECTURE.md" \
  || grep -Fq "separate server" "$ROOT/docs/KB093_JUNEXIS_HARDENED_ON_PREM_APPLIANCE_ARCHITECTURE.md"; then
  pass "KB-093 documents separate Appliance Management server"
else
  fail "KB-093 missing separate Appliance Management server note"
fi

if grep -Fq "TheHive" "$ROOT/junexis-appliance/ansible/roles/minimize/tasks/main.yml"; then
  fail "minimize role must not reference installing TheHive"
else
  pass "minimize role does not install TheHive"
fi

CLI=(python3 -m junexis_cli)

"${CLI[@]}" version >/dev/null && pass "cli version" || fail "cli version"

DOC="$("${CLI[@]}" doctor --json)"
echo "$DOC" | grep -q '"thehive_on_appliance": false' && pass "doctor thehive_on_appliance false" || fail "doctor thehive"
echo "$DOC" | grep -q 'separate_server' && pass "doctor separate appliance mgmt" || fail "doctor separate mgmt"

"${CLI[@]}" setup --token "test-token-not-real-abcdefgh" --appliance-name "B1-TEST" \
  --deploy-method customer-vm --json >/dev/null && pass "cli setup" || fail "cli setup"

MODE="$(cat "$JUNEXIS_STATE_DIR/network_mode")"
[[ "$MODE" == "bootstrap" ]] && pass "after setup mode=bootstrap" || fail "expected bootstrap mode got $MODE"

# Must refuse lock before successful bootstrap
if "${CLI[@]}" network lock --yes >/dev/null 2>&1; then
  fail "lock should fail before bootstrap success"
else
  pass "lock refused before bootstrap success"
fi

"${CLI[@]}" bootstrap update --dry-run --json >/dev/null && pass "bootstrap dry-run" || fail "bootstrap dry-run"
RESULT="$(python3 -c "import json;print(json.load(open('$JUNEXIS_STATE_DIR/bootstrap.json'))['last_result'])")"
[[ "$RESULT" == "success" ]] && pass "bootstrap last_result success" || fail "bootstrap result=$RESULT"

"${CLI[@]}" network lock --yes --dry-run --json >/dev/null && pass "network lock dry-run" || fail "network lock"
MODE="$(cat "$JUNEXIS_STATE_DIR/network_mode")"
[[ "$MODE" == "locked" ]] && pass "after lock mode=locked" || fail "expected locked got $MODE"

STAT="$("${CLI[@]}" status --json)"
echo "$STAT" | grep -q '"handoff_ready": true' && pass "handoff_ready true" || fail "handoff_ready"
echo "$STAT" | grep -q 'not permanent on mssp-control' && pass "status notes mgmt split" || fail "status mgmt split"

# Token must not be stored raw
if grep -Rq "test-token-not-real-abcdefgh" "$JUNEXIS_STATE_DIR"; then
  fail "raw token written to state"
else
  pass "raw token not stored"
fi

"${CLI[@]}" network unlock --yes --confirm BREAK_GLASS --dry-run --json >/dev/null && pass "break-glass unlock" || fail "unlock"
MODE="$(cat "$JUNEXIS_STATE_DIR/network_mode")"
[[ "$MODE" == "bootstrap" ]] && pass "after unlock mode=bootstrap" || fail "expected bootstrap after unlock"

# Architecture validator still passes
"$ROOT/scripts/kb093_validate_junexis_appliance_architecture.sh" >/tmp/kb093-out.txt
tail -1 /tmp/kb093-out.txt | grep -q PASSED && pass "kb093 architecture validator" || fail "kb093 architecture validator"

if [[ "$FAIL" -ne 0 ]]; then
  echo "KB-093 B1 JUNEXIS CLI BOOTSTRAP-LOCK VALIDATION FAILED"
  exit 1
fi
echo "KB-093 B1 JUNEXIS CLI BOOTSTRAP-LOCK VALIDATION PASSED"
