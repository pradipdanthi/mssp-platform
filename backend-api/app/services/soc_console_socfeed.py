"""SOC-analyst focused feed + KPI strip (alerts, incidents, events, vulns, patch gaps).

Keeps the console simple: only what a daily SOC analyst needs — not engine topology.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.session import fetch_all, fetch_one


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _item(
    *,
    id: str,
    kind: str,
    category: str,
    title: str,
    detail: str,
    severity: str,
    ts: Optional[str],
    source: str,
    alert_id: Optional[str] = None,
    incident_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": id,
        "kind": kind,
        "category": category,
        "title": (title or "Event")[:240],
        "detail": (detail or "")[:400],
        "severity": (severity or "info").lower(),
        "alert_id": alert_id,
        "incident_id": incident_id,
        "actor": source,
        "ts": ts or _utc_now(),
        "source": source,
    }


def build_soc_kpis() -> Dict[str, int]:
    row = fetch_one(
        """
        SELECT
          (SELECT COUNT(*)::int FROM security_alerts
             WHERE status NOT IN ('closed','false_positive')) AS alerts,
          (SELECT COUNT(*)::int FROM incidents
             WHERE status IN ('open','in_progress','waiting_customer')) AS incidents,
          (SELECT COUNT(*)::int FROM secure_edge_events
             WHERE created_at > now() - interval '24 hours') AS events_edge,
          (SELECT COUNT(*)::int FROM security_alerts
             WHERE lower(coalesce(source_tool,'')) IN ('suricata','zeek','ndr')
               AND created_at > now() - interval '24 hours') AS events_ndr,
          (SELECT COUNT(*)::int FROM tenant_vulnerability_findings
             WHERE status = 'OPEN') AS vulnerabilities,
          (SELECT COUNT(*)::int FROM sca_check_details
             WHERE upper(status) IN ('FAILED','FAIL')) AS patch_gaps;
        """
    ) or {}
    events = int(row.get("events_edge") or 0) + int(row.get("events_ndr") or 0)
    return {
        "alerts": int(row.get("alerts") or 0),
        "incidents": int(row.get("incidents") or 0),
        "events": events,
        "vulnerabilities": int(row.get("vulnerabilities") or 0),
        "patch_gaps": int(row.get("patch_gaps") or 0),
    }


def list_soc_feed(*, limit: int = 80) -> List[Dict[str, Any]]:
    """Unified SOC feed — only analyst-critical categories."""
    per = max(10, min(25, limit // 4))
    items: List[Dict[str, Any]] = []

    alerts = fetch_all(
        """
        SELECT id::text AS id, alert_title AS title, severity, status, source_tool,
               destination_host,
               (created_at AT TIME ZONE 'utc')::text AS ts
        FROM security_alerts
        WHERE status NOT IN ('closed','false_positive')
        ORDER BY
          CASE lower(severity)
            WHEN 'critical' THEN 0 WHEN 'high' THEN 1
            WHEN 'medium' THEN 2 ELSE 3 END,
          created_at DESC
        LIMIT %s;
        """,
        (per,),
    )
    for a in alerts or []:
        items.append(
            _item(
                id=f"alert-{a['id']}",
                kind="alert",
                category="alert",
                title=a.get("title") or "Security alert",
                detail=f"{a.get('source_tool') or '—'} · {a.get('destination_host') or '—'} · {a.get('status')}",
                severity=a.get("severity") or "info",
                ts=a.get("ts"),
                source="security_alerts",
                alert_id=a["id"],
            )
        )

    incidents = fetch_all(
        """
        SELECT id::text AS id, incident_number, title, severity, status,
               (created_at AT TIME ZONE 'utc')::text AS ts
        FROM incidents
        WHERE status IN ('open','in_progress','waiting_customer')
        ORDER BY created_at DESC
        LIMIT %s;
        """,
        (max(8, per // 2),),
    )
    for i in incidents or []:
        items.append(
            _item(
                id=f"inc-{i['id']}",
                kind="incident",
                category="incident",
                title=f"{i.get('incident_number')}: {i.get('title')}",
                detail=f"status={i.get('status')}",
                severity=i.get("severity") or "medium",
                ts=i.get("ts"),
                source="incidents",
                incident_id=i["id"],
            )
        )

    # Events = Secure Edge + NDR (Suricata/Zeek) alerts
    edge = fetch_all(
        """
        SELECT id::text AS id, event_type, severity, summary, public_hostname,
               (created_at AT TIME ZONE 'utc')::text AS ts
        FROM secure_edge_events
        ORDER BY created_at DESC
        LIMIT %s;
        """,
        (max(8, per // 2),),
    )
    for e in edge or []:
        items.append(
            _item(
                id=f"edge-{e['id']}",
                kind="event",
                category="event",
                title=f"Edge · {e.get('event_type') or 'event'}",
                detail=f"{e.get('summary') or '—'} · {e.get('public_hostname') or '—'}",
                severity=e.get("severity") or "info",
                ts=e.get("ts"),
                source="secure_edge_events",
            )
        )

    ndr = fetch_all(
        """
        SELECT id::text AS id, alert_title AS title, severity, source_tool, destination_host,
               (created_at AT TIME ZONE 'utc')::text AS ts
        FROM security_alerts
        WHERE lower(coalesce(source_tool,'')) IN ('suricata','zeek','ndr')
        ORDER BY created_at DESC
        LIMIT %s;
        """,
        (max(8, per // 2),),
    )
    for a in ndr or []:
        items.append(
            _item(
                id=f"ndr-{a['id']}",
                kind="event",
                category="event",
                title=f"NDR · {a.get('title') or 'network event'}",
                detail=f"{a.get('source_tool')} · {a.get('destination_host') or '—'}",
                severity=a.get("severity") or "info",
                ts=a.get("ts"),
                source="ndr",
                alert_id=a["id"],
            )
        )

    vulns = fetch_all(
        """
        SELECT id::text AS id, title, severity, cve_id, asset_ip_or_host, status,
               (updated_at AT TIME ZONE 'utc')::text AS ts
        FROM tenant_vulnerability_findings
        WHERE status = 'OPEN'
        ORDER BY
          CASE upper(severity)
            WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1
            WHEN 'MEDIUM' THEN 2 ELSE 3 END,
          updated_at DESC
        LIMIT %s;
        """,
        (max(8, per // 2),),
    )
    for v in vulns or []:
        items.append(
            _item(
                id=f"vuln-{v['id']}",
                kind="vulnerability",
                category="vulnerability",
                title=v.get("title") or "Vulnerability",
                detail=f"{v.get('cve_id') or '—'} · host {v.get('asset_ip_or_host') or '—'}",
                severity=(v.get("severity") or "info").lower(),
                ts=v.get("ts"),
                source="vulnerabilities",
            )
        )

    patches = fetch_all(
        """
        SELECT id::text AS id, rule_title, severity, status, check_id,
               (updated_at AT TIME ZONE 'utc')::text AS ts
        FROM sca_check_details
        WHERE upper(status) IN ('FAILED','FAIL')
        ORDER BY
          CASE lower(severity)
            WHEN 'critical' THEN 0 WHEN 'high' THEN 1
            WHEN 'medium' THEN 2 ELSE 3 END,
          updated_at DESC
        LIMIT %s;
        """,
        (max(8, per // 2),),
    )
    for p in patches or []:
        items.append(
            _item(
                id=f"patch-{p['id']}",
                kind="patch_gap",
                category="patch_gap",
                title=p.get("rule_title") or f"Patch gap {p.get('check_id')}",
                detail=f"SCA {p.get('status')} · {p.get('check_id') or '—'}",
                severity=(p.get("severity") or "medium").lower(),
                ts=p.get("ts"),
                source="sca_patch_gaps",
            )
        )

    items.sort(key=lambda x: str(x.get("ts") or ""), reverse=True)
    return items[:limit]
