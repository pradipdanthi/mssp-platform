"""SOC Console system skeleton — live pulse of the MSSP stack.

Data-driven status (no engine probing / no schema changes). Uses DB signals
plus control-plane Redis/Postgres health so the console can show the "DNS /
skeleton" of the platform continuously.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.session import fetch_all, fetch_one, redis_client
from app.services.soc_agent_client import soc_agent_enabled
from app.services.soc_console_chat import soc_console_chat_enabled

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _node(
    *,
    id: str,
    label: str,
    layer: str,
    status: str,
    detail: str,
    pulse: int = 0,
    metric: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "layer": layer,
        "status": status,  # ok | warn | critical | idle | unknown
        "detail": detail[:240],
        "pulse": int(pulse or 0),
        "metric": metric,
    }


def _tool_activity(hours: int = 24) -> Dict[str, int]:
    rows = fetch_all(
        """
        SELECT lower(coalesce(nullif(trim(source_tool), ''), 'unknown')) AS tool,
               COUNT(*)::int AS n
        FROM security_alerts
        WHERE created_at > now() - make_interval(hours => %s)
        GROUP BY 1
        ORDER BY n DESC;
        """,
        (hours,),
    )
    return {str(r["tool"]): int(r["n"]) for r in (rows or [])}


def _status_from_count(n: int, *, warn_at: int = 1, ok_idle: bool = True) -> str:
    if n >= warn_at:
        return "ok"
    return "idle" if ok_idle else "unknown"


def build_stack_skeleton() -> Dict[str, Any]:
    """Return topology nodes + edges + KPI strip for the SOC console."""
    db_ok = False
    redis_ok = False
    try:
        row = fetch_one("SELECT 1 AS ok;")
        db_ok = bool(row and row.get("ok") == 1)
    except Exception:  # noqa: BLE001
        logger.exception("stack skeleton database check failed")
    try:
        redis_ok = bool(redis_client().ping())
    except Exception:  # noqa: BLE001
        logger.exception("stack skeleton redis check failed")

    kpis = fetch_one(
        """
        SELECT
          (SELECT COUNT(*)::int FROM security_alerts
             WHERE created_at > now() - interval '1 hour') AS alerts_1h,
          (SELECT COUNT(*)::int FROM security_alerts
             WHERE created_at > now() - interval '24 hours') AS alerts_24h,
          (SELECT COUNT(*)::int FROM security_alerts
             WHERE severity IN ('high','critical')
               AND status NOT IN ('closed','false_positive')) AS high_open,
          (SELECT COUNT(*)::int FROM incidents
             WHERE status IN ('open','in_progress')) AS open_incidents,
          (SELECT COUNT(*)::int FROM secure_edge_events
             WHERE created_at > now() - interval '24 hours') AS edge_24h,
          (SELECT COUNT(*)::int FROM appliances
             WHERE status = 'online') AS appliances_online,
          (SELECT COUNT(*)::int FROM appliances
             WHERE status IN ('registered','offline','maintenance')) AS appliances_other,
          (SELECT COUNT(*)::int FROM appliance_heartbeats
             WHERE heartbeat_at > now() - interval '15 minutes') AS heartbeats_15m,
          (SELECT COUNT(*)::int FROM notification_events
             WHERE created_at > now() - interval '24 hours') AS notify_24h,
          (SELECT COUNT(*)::int FROM audit_logs
             WHERE created_at > now() - interval '1 hour') AS audit_1h,
          (SELECT COUNT(*)::int FROM security_alerts
             WHERE ai_verdict IS NOT NULL
               AND updated_at > now() - interval '24 hours') AS ai_triaged_24h,
          (SELECT COUNT(*)::int FROM customer_recommendations
             WHERE created_at > now() - interval '24 hours') AS recs_24h,
          (SELECT COUNT(*)::int FROM tenants WHERE status = 'active') AS active_tenants;
        """
    ) or {}

    tools = _tool_activity(24)

    def tool_pulse(*names: str) -> int:
        return sum(int(tools.get(n, 0)) for n in names)

    def tool_status(*names: str) -> str:
        n = tool_pulse(*names)
        if n > 0:
            return "ok"
        return "idle"

    cp_status = "ok" if db_ok and redis_ok else ("warn" if db_ok or redis_ok else "critical")
    agent_on = soc_agent_enabled()
    chat_on = soc_console_chat_enabled()

    nodes: List[Dict[str, Any]] = [
        _node(
            id="admin_portal",
            label="Admin Portal",
            layer="frontend",
            status="ok",
            detail=":3000 nginx · SOC/Admin UI",
            pulse=int(kpis.get("audit_1h") or 0),
            metric="ops UI",
        ),
        _node(
            id="customer_portal",
            label="Customer Portal",
            layer="frontend",
            status="ok",
            detail=":3001 nginx · tenant UI",
            pulse=int(kpis.get("recs_24h") or 0),
            metric="tenant UI",
        ),
        _node(
            id="soc_console",
            label="SOC Console",
            layer="frontend",
            status="ok",
            detail=":3002 · live ops + Cursor AI",
            pulse=int(kpis.get("ai_triaged_24h") or 0),
            metric="live feed",
        ),
        _node(
            id="control_plane",
            label="Control Plane API",
            layer="core",
            status=cp_status,
            detail=f"API · DB={'ok' if db_ok else 'down'} · Redis={'ok' if redis_ok else 'down'}",
            pulse=int(kpis.get("alerts_1h") or 0),
            metric=f"{kpis.get('alerts_1h') or 0}/h alerts",
        ),
        _node(
            id="postgres",
            label="PostgreSQL",
            layer="core",
            status="ok" if db_ok else "critical",
            detail="System of record",
            pulse=int(kpis.get("alerts_24h") or 0),
            metric="records",
        ),
        _node(
            id="redis",
            label="Redis",
            layer="core",
            status="ok" if redis_ok else "critical",
            detail="Cache / queues",
            pulse=0,
            metric="queue",
        ),
        _node(
            id="wazuh",
            label="Wazuh / EDR",
            layer="engine",
            status=tool_status("wazuh", "edr", "syscheck", "fim"),
            detail="Endpoint + log engine",
            pulse=tool_pulse("wazuh", "edr", "syscheck", "fim"),
            metric=f"{tool_pulse('wazuh', 'edr', 'syscheck', 'fim')} /24h",
        ),
        _node(
            id="ndr",
            label="NDR (Suricata/Zeek)",
            layer="engine",
            status=tool_status("suricata", "zeek", "ndr"),
            detail="Network detection",
            pulse=tool_pulse("suricata", "zeek", "ndr"),
            metric=f"{tool_pulse('suricata', 'zeek', 'ndr')} /24h",
        ),
        _node(
            id="case_soar",
            label="Case / SOAR",
            layer="engine",
            status=tool_status("thehive", "shuffle", "soar"),
            detail="TheHive + Shuffle",
            pulse=tool_pulse("thehive", "shuffle", "soar") + int(kpis.get("open_incidents") or 0),
            metric=f"{kpis.get('open_incidents') or 0} open",
        ),
        _node(
            id="secure_edge",
            label="Secure Edge",
            layer="engine",
            status=_status_from_count(int(kpis.get("edge_24h") or 0)),
            detail="Perimeter / WAF events",
            pulse=int(kpis.get("edge_24h") or 0),
            metric=f"{kpis.get('edge_24h') or 0} /24h",
        ),
        _node(
            id="vuln",
            label="Vuln / EASM",
            layer="engine",
            status=tool_status("greenbone", "nuclei", "vuls", "amass", "openvas"),
            detail="Scan adapters",
            pulse=tool_pulse("greenbone", "nuclei", "vuls", "amass", "openvas"),
            metric=f"{tool_pulse('greenbone', 'nuclei', 'vuls', 'amass', 'openvas')} /24h",
        ),
        _node(
            id="identity",
            label="Identity / ITDR",
            layer="engine",
            status=tool_status("entra", "m365", "azuread", "identity", "itdr"),
            detail="Entra / M365 telemetry",
            pulse=tool_pulse("entra", "m365", "azuread", "identity", "itdr"),
            metric=f"{tool_pulse('entra', 'm365', 'azuread', 'identity', 'itdr')} /24h",
        ),
        _node(
            id="soc_agent",
            label="SOC Agent (Cursor)",
            layer="ai",
            status="ok" if agent_on and chat_on else ("warn" if agent_on else "idle"),
            detail="Deep triage · console chat",
            pulse=int(kpis.get("ai_triaged_24h") or 0),
            metric="Cursor" if chat_on else "offline",
        ),
        _node(
            id="appliances",
            label="Customer Appliances",
            layer="edge",
            status=(
                "ok"
                if int(kpis.get("appliances_online") or 0) > 0
                else ("warn" if int(kpis.get("heartbeats_15m") or 0) > 0 else "idle")
            ),
            detail=f"{kpis.get('appliances_online') or 0} online · {kpis.get('heartbeats_15m') or 0} HB/15m",
            pulse=int(kpis.get("heartbeats_15m") or 0),
            metric=f"{kpis.get('appliances_online') or 0} online",
        ),
        _node(
            id="notify",
            label="Notifications",
            layer="ops",
            status=_status_from_count(int(kpis.get("notify_24h") or 0)),
            detail="Email / WhatsApp / webhook queue",
            pulse=int(kpis.get("notify_24h") or 0),
            metric=f"{kpis.get('notify_24h') or 0} /24h",
        ),
    ]

    edges = [
        {"from": "admin_portal", "to": "control_plane"},
        {"from": "customer_portal", "to": "control_plane"},
        {"from": "soc_console", "to": "control_plane"},
        {"from": "soc_console", "to": "soc_agent"},
        {"from": "control_plane", "to": "postgres"},
        {"from": "control_plane", "to": "redis"},
        {"from": "wazuh", "to": "control_plane"},
        {"from": "ndr", "to": "control_plane"},
        {"from": "case_soar", "to": "control_plane"},
        {"from": "secure_edge", "to": "control_plane"},
        {"from": "vuln", "to": "control_plane"},
        {"from": "identity", "to": "control_plane"},
        {"from": "appliances", "to": "control_plane"},
        {"from": "soc_agent", "to": "control_plane"},
        {"from": "control_plane", "to": "notify"},
    ]

    return {
        "generated_at": _utc_now(),
        "kpis": {
            "alerts_1h": int(kpis.get("alerts_1h") or 0),
            "alerts_24h": int(kpis.get("alerts_24h") or 0),
            "high_open": int(kpis.get("high_open") or 0),
            "open_incidents": int(kpis.get("open_incidents") or 0),
            "edge_24h": int(kpis.get("edge_24h") or 0),
            "appliances_online": int(kpis.get("appliances_online") or 0),
            "heartbeats_15m": int(kpis.get("heartbeats_15m") or 0),
            "ai_triaged_24h": int(kpis.get("ai_triaged_24h") or 0),
            "notify_24h": int(kpis.get("notify_24h") or 0),
            "audit_1h": int(kpis.get("audit_1h") or 0),
            "active_tenants": int(kpis.get("active_tenants") or 0),
            "recs_24h": int(kpis.get("recs_24h") or 0),
        },
        "tool_activity_24h": tools,
        "nodes": nodes,
        "edges": edges,
        "layers": ["frontend", "core", "engine", "ai", "edge", "ops"],
    }
