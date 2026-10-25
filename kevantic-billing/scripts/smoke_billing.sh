#!/usr/bin/env bash
# Smoke test for standalone kevantic-billing (does not touch mssp-control).
set -euo pipefail
BASE="${BILLING_BASE_URL:-http://127.0.0.1:8090}"
CREDS_FILE="${BILLING_CREDS_FILE:-/opt/mssp-control/kevantic-billing/data/OPERATOR_CREDS.txt}"

curl -fsS "$BASE/health" | grep -q '"status":"ok"'
echo "PASS health"

if [[ ! -f "$CREDS_FILE" ]]; then
  echo "WARN: no creds file at $CREDS_FILE — skipping auth smoke"
  exit 0
fi
USER=$(grep '^USER=' "$CREDS_FILE" | cut -d= -f2)
PASS=$(grep '^PASSWORD=' "$CREDS_FILE" | cut -d= -f2)
AUTH=$(printf '%s:%s' "$USER" "$PASS" | base64 -w0)

COUNT=$(curl -fsS -H "Authorization: Basic $AUTH" "$BASE/api/catalog" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))')
[[ "$COUNT" -ge 8 ]] || { echo "FAIL catalog count $COUNT"; exit 1; }
echo "PASS catalog ($COUNT SKUs)"

# Portals must still respond if this host is the control plane
if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "PASS mssp /health still up"
fi
echo "ALL SMOKE CHECKS PASSED"
