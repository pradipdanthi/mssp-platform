#!/usr/bin/env bash
# KB-061: pull TheHive alerts (MSSP-Lab) into control plane SOC sync API.
# Secrets: TheHive password via THEHIVE_PASSWORD env; sync key via file/env. Never commit.
set -euo pipefail

THEHIVE_URL="${THEHIVE_URL:-http://192.168.0.212:9000}"
THEHIVE_USER="${THEHIVE_USER:-admin@thehive.local}"
THEHIVE_ORG="${THEHIVE_ORG:-MSSP-Lab}"
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:8000}"
TENANT_SHORT_CODE="${TENANT_SHORT_CODE:-DEMO}"

if [[ -z "${THEHIVE_PASSWORD:-}" ]]; then
  echo "Set THEHIVE_PASSWORD (not committed)." >&2
  exit 1
fi

if [[ -n "${SOC_SYNC_API_KEY:-}" ]]; then
  SYNC_KEY="$SOC_SYNC_API_KEY"
elif [[ -f /opt/mssp-control/.secrets/soc_sync_api_key ]]; then
  SYNC_KEY="$(tr -d '\n' </opt/mssp-control/.secrets/soc_sync_api_key)"
else
  echo "SOC sync key missing (SOC_SYNC_API_KEY or .secrets/soc_sync_api_key)." >&2
  exit 1
fi

map_severity() {
  case "$1" in
    4|critical|Critical) echo critical ;;
    3|high|High) echo high ;;
    2|medium|Medium) echo medium ;;
    *) echo low ;;
  esac
}

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

curl -fsS --max-time 30 -u "${THEHIVE_USER}:${THEHIVE_PASSWORD}" \
  -H "X-Organisation: ${THEHIVE_ORG}" \
  -H 'Content-Type: application/json' \
  -d '{"query":[{"_name":"listAlert"}]}' \
  "${THEHIVE_URL}/api/v1/query" >"$TMP"

python3 - "$TMP" "$CONTROL_PLANE_URL" "$SYNC_KEY" "$TENANT_SHORT_CODE" <<'PY'
import json, sys, urllib.request

path, base, key, tenant = sys.argv[1:5]
alerts = json.loads(open(path, encoding="utf-8").read())
if not isinstance(alerts, list):
    raise SystemExit(f"unexpected TheHive response: {type(alerts)}")

def sev(v):
    try:
        n = int(v)
    except Exception:
        n = 2
    return {4: "critical", 3: "high", 2: "medium"}.get(n, "low")

ok = dup = fail = 0
for a in alerts:
    ext = str(a.get("_id") or a.get("id") or "")
    if not ext:
        continue
    title = (a.get("title") or "TheHive alert")[:500]
    desc = (a.get("description") or a.get("summary") or "")[:4000] or None
    tags = a.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    tags_l = [str(x).lower() for x in tags]
    atype = str(a.get("type") or "").lower()
    source = str(a.get("source") or "").lower()
    wazuhish = (
        "wazuh" in tags_l
        or atype == "wazuh"
        or "wazuh" in source
        or "wazuh" in title.lower()
    )
    severity = "high" if wazuhish else sev(a.get("severity", 2))
    body = {
        "source_tool": "thehive",
        "external_alert_id": ext,
        "severity": severity,
        "alert_title": title,
        "alert_description": desc,
        "tenant_short_code": tenant,
        "create_incident": True if wazuhish or severity in ("high", "critical") else False,
        "customer_visible_summary": f"SOC is reviewing: {title}"[:4000],
        "business_impact": "Under SOC investigation. Details appear when approved for customer view.",
    }
    req = urllib.request.Request(
        base.rstrip("/") + "/integrations/soc/sync",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "X-SOC-Sync-Key": key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            if data.get("duplicate"):
                dup += 1
                print(f"DUP {ext} alert={data.get('alert_id')} incident={data.get('incident_number')}")
            else:
                ok += 1
                print(f"OK  {ext} alert={data.get('alert_id')} incident={data.get('incident_number')}")
    except Exception as e:
        fail += 1
        print(f"FAIL {ext}: {e}")

print(f"SUMMARY ok={ok} duplicate={dup} fail={fail} total={len(alerts)}")
if fail:
    raise SystemExit(1)
PY
