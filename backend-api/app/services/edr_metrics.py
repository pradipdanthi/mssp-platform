"""KB-083: EDR metrics and read models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.session import fetch_all, fetch_one
from app.schemas.edr import EdrMetricsSummary
from app.services.edr_mitre import customer_safe_mitre
from app.services.edr_process_tree import build_process_forest


def get_edr_metrics(*, tenant_id: Optional[str] = None) -> EdrMetricsSummary:
    params: tuple = ()
    tenant_filter = ""
    if tenant_id:
        tenant_filter = "AND tenant_id = %s::uuid"
        params = (tenant_id,)

    mttc = fetch_one(
        f"""
        WITH isolations AS (
            SELECT e.incident_id, MIN(e.created_at) AS isolated_at
            FROM edr_action_executions e
            WHERE e.action_type = 'ISOLATE_HOST'
              AND e.status IN ('executed', 'success', 'verified')
              {tenant_filter.replace('tenant_id', 'e.tenant_id')}
            GROUP BY e.incident_id
        ),
        pairs AS (
            SELECT EXTRACT(EPOCH FROM (i.isolated_at - a.created_at)) AS seconds
            FROM isolations i
            JOIN incidents inc ON inc.id = i.incident_id
            JOIN security_alerts a ON a.id = inc.primary_alert_id
            WHERE i.isolated_at >= a.created_at
        )
        SELECT AVG(seconds)::float AS mttc FROM pairs;
        """,
        params,
    )
    telemetry = fetch_one(
        f"""
        SELECT COALESCE(SUM(events_processed), 0)::bigint AS total
        FROM edr_telemetry_stats
        WHERE 1=1 {tenant_filter};
        """,
        params,
    )
    isolated = fetch_one(
        f"""
        SELECT count(*)::int AS c FROM edr_endpoint_isolation
        WHERE 1=1 {tenant_filter}
          AND COALESCE(isolation_status, 'isolated') = 'isolated';
        """,
        params,
    )
    return EdrMetricsSummary(
        mean_time_to_contain_seconds=(mttc or {}).get("mttc"),
        telemetry_events_processed=int((telemetry or {}).get("total") or 0),
        isolated_endpoints_count=int((isolated or {}).get("c") or 0),
    )


def load_incident_raw_events(tenant_id: str, incident_id: str) -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT sa.raw_event
        FROM incident_alerts ia
        JOIN security_alerts sa ON sa.id = ia.alert_id
        WHERE ia.incident_id = %s::uuid AND sa.tenant_id = %s::uuid;
        """,
        (incident_id, tenant_id),
    )
    events: List[Dict[str, Any]] = []
    for row in rows:
        raw = row.get("raw_event")
        if isinstance(raw, dict):
            events.append(raw)
    return events


def endpoint_context_from_events(raw_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not raw_events:
        return {
            "hostname": None,
            "os_version": None,
            "agent_id": None,
            "local_ip": None,
            "logged_in_user": None,
            "sysmon_detail": None,
        }
    raw = raw_events[0]
    agent = raw.get("agent") if isinstance(raw.get("agent"), dict) else {}
    os_info = agent.get("os") if isinstance(agent.get("os"), dict) else {}
    return {
        "hostname": agent.get("name"),
        "os_version": f"{os_info.get('name', '')} {os_info.get('version', '')}".strip() or None,
        "agent_id": agent.get("id"),
        "local_ip": agent.get("ip"),
        "logged_in_user": raw.get("syscheck", {}).get("uname") if isinstance(raw.get("syscheck"), dict) else None,
        "sysmon_detail": "Process creation telemetry present"
        if "sysmon" in str(raw).lower()
        else None,
    }


def merged_mitre_for_incident(tenant_id: str, incident_id: str) -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT sa.mitre_mapping
        FROM incident_alerts ia
        JOIN security_alerts sa ON sa.id = ia.alert_id
        WHERE ia.incident_id = %s::uuid AND sa.tenant_id = %s::uuid;
        """,
        (incident_id, tenant_id),
    )
    tactics: List[str] = []
    techniques: List[Dict[str, str]] = []
    seen = set()
    for row in rows:
        safe = customer_safe_mitre(row.get("mitre_mapping"))
        for t in safe.get("tactics") or []:
            if t not in seen:
                seen.add(t)
                tactics.append(t)
        for tech in safe.get("techniques") or []:
            key = tech.get("id")
            if key and key not in seen:
                seen.add(key)
                techniques.append(tech)
    return {"tactics": tactics, "techniques": techniques}
