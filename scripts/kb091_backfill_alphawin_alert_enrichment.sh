#!/usr/bin/env bash
# KB-091: Backfill Alpha-Win alert enrichment (asset/IP/user/taxonomy/tech summary).
set -euo pipefail
cd /opt/mssp-control

docker exec -i mssp-backend-api python3 - <<'PY'
import json
from app.db.session import db_transaction
from app.services.edr_ingress import persist_wazuh_alert_enrichment
from app.services.soc_alert_taxonomy import enrich_alert_row

TENANT = "ALPHAWINCORP-6VS2"

with db_transaction() as cur:
    cur.execute(
        "SELECT id::text AS id FROM tenants WHERE short_code=%s",
        (TENANT,),
    )
    tenant = cur.fetchone()
    if not tenant:
        raise SystemExit(f"tenant {TENANT} not found")
    tenant_id = tenant["id"]

    cur.execute(
        """
        SELECT id::text AS id, hostname, os_name, host(ip_address)::text AS ip,
               details->>'wazuh_agent_id' AS agent_id
        FROM protected_assets
        WHERE tenant_id=%s::uuid AND lower(hostname)=lower('WIN-BL72S84GDTF')
        LIMIT 1;
        """,
        (tenant_id,),
    )
    asset = cur.fetchone()
    if not asset:
        raise SystemExit("protected asset WIN-BL72S84GDTF not found")

    cur.execute(
        """
        SELECT id::text AS id, external_alert_id, raw_event, destination_host
        FROM security_alerts
        WHERE tenant_id=%s::uuid
        ORDER BY created_at;
        """,
        (tenant_id,),
    )
    alerts = cur.fetchall()

# Prefer a real Wazuh raw_event as a template for the restored reference row.
template_raw = None
for a in alerts:
    raw = a["raw_event"]
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if isinstance(raw, dict) and raw.get("agent") and raw.get("rule"):
        template_raw = raw
        break

for a in alerts:
    raw = a["raw_event"]
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}

    if not raw.get("agent"):
        # Synthetic evidence for restored reference ticker (TH-0003).
        raw = {
            "id": a["external_alert_id"],
            "rule": {
                "id": "92213",
                "level": 15,
                "description": "Executable file dropped in folder commonly used by malware",
                "groups": ["windows", "sysmon", "sysmon_eid_11"],
            },
            "agent": {
                "id": asset["agent_id"] or "006",
                "name": asset["hostname"],
                "ip": asset["ip"],
                "os": {"name": asset["os_name"] or "Microsoft Windows Server"},
            },
            "data": {
                "win": {
                    "eventdata": {
                        "targetFilename": (
                            "C:/Users/Administrator/AppData/Local/Temp/2/"
                            "__PSScriptPolicyTest_remedi_reference.ps1"
                        ),
                        "User": "NT AUTHORITY\\SYSTEM",
                    }
                }
            },
            "decoder": {"name": "windows_eventchannel"},
            "location": "EventChannel",
            "timestamp": "2026-07-30T11:34:44.000+0530",
            "_mssp_note": "Synthesized for KB-091 reference ticker backfill",
        }
        if template_raw and isinstance(template_raw.get("manager"), dict):
            raw["manager"] = template_raw["manager"]

    persist_wazuh_alert_enrichment(a["id"], tenant_id, raw)
    print(f"enriched alert {a['external_alert_id']}")

with db_transaction() as cur:
    cur.execute(
        """
        SELECT
            sa.external_alert_id,
            sa.source_user,
            sa.source_ip::text,
            sa.destination_ip::text,
            pa.hostname AS asset_hostname,
            sa.ai_technical_summary IS NOT NULL AS has_tech,
            sa.raw_event,
            pa.os_name AS asset_os_name,
            pa.hostname AS asset_hostname,
            sa.destination_host,
            sa.source_tool,
            sa.alert_title
        FROM security_alerts sa
        LEFT JOIN protected_assets pa ON pa.id = sa.asset_id
        WHERE sa.tenant_id=%s::uuid
        ORDER BY sa.created_at;
        """,
        (tenant_id,),
    )
    for row in cur.fetchall():
        d = dict(row)
        raw = d.pop("raw_event")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        d["raw_event"] = raw if isinstance(raw, dict) else {}
        e = enrich_alert_row(d)
        print(
            d["external_alert_id"],
            "asset=", d.get("asset_hostname"),
            "cat=", e["asset_category"],
            "dev=", e["device_type"],
            "ip=", d.get("destination_ip"),
            "user=", d.get("source_user"),
            "tech=", "yes" if d.get("has_tech") else "no",
        )
print("BACKFILL_OK")
PY
