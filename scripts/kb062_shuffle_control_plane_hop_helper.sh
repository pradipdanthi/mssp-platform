#!/usr/bin/env bash
# KB-062 helper: show/copy the HTTP action Shuffle should call after TheHive create.
# Does not modify Shuffle automatically (needs UI/API key). Never prints the sync key.
set -euo pipefail
cd /opt/mssp-control

CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://192.168.0.201:8000}"
KEY_FILE="${SOC_SYNC_API_KEY_FILE:-/opt/mssp-control/.secrets/soc_sync_api_key}"

if [[ ! -f "$KEY_FILE" ]]; then
  echo "Missing sync key file: $KEY_FILE" >&2
  exit 1
fi

echo "Add an HTTP request step in Shuffle AFTER TheHive create:"
echo "  Method : POST"
echo "  URL    : ${CONTROL_PLANE_URL}/integrations/soc/sync"
echo "  Header : X-SOC-Sync-Key: <value from $KEY_FILE — paste in Shuffle only>"
echo "  Header : Content-Type: application/json"
echo
echo "Body template (paste into Shuffle HTTP body):"
cat <<'JSON'
{
  "source_tool": "thehive",
  "external_alert_id": "REPLACE_WITH_THEHIVE_ALERT_ID",
  "severity": "high",
  "alert_title": "REPLACE_WITH_TITLE",
  "alert_description": "Synced from Shuffle after TheHive create",
  "tenant_short_code": "DEMO",
  "create_incident": true,
  "customer_visible_summary": "SOC is reviewing this alert.",
  "business_impact": "Under SOC investigation. Details appear when approved for customer view."
}
JSON
echo
echo "Until the Shuffle hop is saved, keep using:"
echo "  ./scripts/kb061_run_periodic_sync.sh"
