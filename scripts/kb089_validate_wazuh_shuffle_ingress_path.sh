#!/usr/bin/env bash
# KB-089: Live regression — Wazuh Shuffle-wrapped webhook → control plane.
# Proves the sellable path, not just "Manager saw the alert".
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-089: Validate Wazuh Shuffle ingress path (wrapped + raw)"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1" >&2
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

section "1. Code contract: unwrap Shuffle all_fields wrapper"

grep -q 'def unwrap_wazuh_ingress_payload' backend-api/app/api/routes/soc_sync.py \
  || fail "missing unwrap_wazuh_ingress_payload helper"
grep -q 'all_fields' backend-api/app/api/routes/soc_sync.py \
  || fail "soc_sync must handle Shuffle all_fields wrapper"
grep -q 'unwrap_wazuh_ingress_payload(raw)' backend-api/app/api/routes/soc_sync.py \
  || fail "wazuh_instant_ingress must call unwrap helper"
echo "OK: ingress unwrap contract present"

section "2. Resolve ingress token (never printed)"

TOKEN=""
if [ -f .secrets/wazuh_ingress_token ]; then
  TOKEN="$(tr -d '\r\n' < .secrets/wazuh_ingress_token)"
elif [ -n "${WAZUH_INGRESS_TOKEN:-}" ]; then
  TOKEN="$WAZUH_INGRESS_TOKEN"
fi
[ -n "$TOKEN" ] || fail "WAZUH_INGRESS_TOKEN / .secrets/wazuh_ingress_token not configured"
echo "OK: ingress token available (value redacted)"

section "3. Unit-shape check inside API container"

docker exec -i mssp-backend-api python3 - <<'PY' || fail "unwrap unit check failed"
from app.api.routes.soc_sync import unwrap_wazuh_ingress_payload

raw = {
    "severity": 3,
    "pretext": "WAZUH Alert",
    "title": "test",
    "rule_id": "92057",
    "all_fields": {
        "rule": {"id": "92057", "level": 12, "description": "encoded"},
        "agent": {"id": "006", "name": "WIN-TEST"},
        "id": "unit-test-id",
    },
}
out = unwrap_wazuh_ingress_payload(raw)
assert out.get("agent", {}).get("id") == "006", out
assert out.get("rule", {}).get("id") == "92057", out
plain = {"rule": {"id": "1"}, "agent": {"id": "001"}}
assert unwrap_wazuh_ingress_payload(plain) is plain or unwrap_wazuh_ingress_payload(plain)["agent"]["id"] == "001"
print("OK: unwrap handles Shuffle wrapper and raw alert")
PY

section "4. Live POST: Shuffle-wrapped payload (production shape)"

UNIQUE="kb089-shuffle-wrap-$(date +%s)"
HOOK_URL="http://127.0.0.1:8000/integrations/soc/hooks/wazuh/${TOKEN}"

RESP="$(curl -fsS -X POST "$HOOK_URL" \
  -H 'Content-Type: application/json' \
  -d "$(cat <<JSON
{
  "severity": 3,
  "pretext": "WAZUH Alert",
  "title": "KB089 Shuffle wrap regression",
  "rule_id": "92057",
  "timestamp": "2026-07-29T18:00:00.000+0000",
  "id": "${UNIQUE}",
  "all_fields": {
    "timestamp": "2026-07-29T18:00:00.000+0000",
    "rule": {
      "level": 12,
      "description": "KB089 Shuffle wrap regression",
      "id": "92057"
    },
    "agent": {
      "id": "006",
      "name": "WIN-BL72S84GDTF",
      "ip": "192.168.0.214"
    },
    "id": "${UNIQUE}",
    "manager": {"name": "wazuh-stack"},
    "decoder": {"name": "windows_eventchannel"}
  }
}
JSON
)")" || fail "Shuffle-wrapped POST failed (curl non-zero). Backend may reject unwrap/tenant mapping."

echo "$RESP" | grep -q '"success": *true' || fail "wrapped POST response missing success=true: $RESP"
echo "$RESP" | grep -q '"alert_id"' || fail "wrapped POST missing alert_id: $RESP"
echo "OK: Shuffle-wrapped ingress accepted"

section "5. Live POST: raw Wazuh alert (direct shape)"

UNIQUE2="kb089-raw-$(date +%s)"
RESP2="$(curl -fsS -X POST "$HOOK_URL" \
  -H 'Content-Type: application/json' \
  -d "$(cat <<JSON
{
  "timestamp": "2026-07-29T18:00:01.000+0000",
  "rule": {
    "level": 12,
    "description": "KB089 raw alert regression",
    "id": "92057"
  },
  "agent": {
    "id": "006",
    "name": "WIN-BL72S84GDTF",
    "ip": "192.168.0.214"
  },
  "id": "${UNIQUE2}",
  "manager": {"name": "wazuh-stack"},
  "decoder": {"name": "windows_eventchannel"}
}
JSON
)")" || fail "raw Wazuh POST failed"

echo "$RESP2" | grep -q '"success": *true' || fail "raw POST response missing success=true: $RESP2"
echo "OK: raw Wazuh ingress accepted"

section "6. Final verdict"

echo
echo "VALIDATION PASSED: Wazuh Shuffle-wrapped AND raw ingress paths work."
echo "This is the sellable path: Manager alert → webhook shape → control plane alert."
exit 0
