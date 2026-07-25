#!/usr/bin/env bash
# KB-069: Ingest one sample Greenbone-style finding into DEMO (or TENANT_SHORT_CODE).
# Reads sync key from gitignored .secrets/vuln_sync_api_key — never prints it.
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

TENANT_SHORT_CODE="${TENANT_SHORT_CODE:-DEMO}"
API_BASE="${API_BASE:-http://localhost:8000}"
KEY_FILE="${VULN_SYNC_API_KEY_FILE:-$PROJECT_DIR/.secrets/vuln_sync_api_key}"

[ -f "$KEY_FILE" ] || {
  echo "Missing $KEY_FILE — create a random key file first (never commit it)." >&2
  exit 1
}
KEY="$(tr -d '[:space:]' < "$KEY_FILE")"
[ -n "$KEY" ] || { echo "Empty sync key file" >&2; exit 1; }

EXT_ID="kb069-sample-$(date -u +%Y%m%d%H%M%S)"

curl -fsS -X POST "$API_BASE/integrations/vuln/sync" \
  -H "Content-Type: application/json" \
  -H "X-Vuln-Sync-Key: $KEY" \
  -d "$(python3 - <<PY
import json
print(json.dumps({
  "tenant_short_code": "$TENANT_SHORT_CODE",
  "source_platform": "greenbone",
  "findings": [{
    "external_finding_id": "$EXT_ID",
    "title": "Outdated OpenSSH package (sample)",
    "severity": "high",
    "cve_id": "CVE-2024-XXXX",
    "nvt_oid": "1.3.6.1.4.1.25623.1.0.999999",
    "asset_hostname": None,
    "customer_safe_summary": "A critical network service on a protected asset may be missing security updates.",
    "remediation_summary": "Apply vendor security updates for OpenSSH during the next maintenance window, then rescan.",
    "create_recommendation": True,
    "recommendation_customer_visible": False
  }]
}))
PY
)" | python3 -m json.tool

echo
echo "Sample finding ingested for $TENANT_SHORT_CODE (recommendation draft, customer_visible=false)."
