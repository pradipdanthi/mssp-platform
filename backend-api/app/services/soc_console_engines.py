"""MSSP stack engine catalog + live reachability for the SOC Hollywood wall.

Probes are short TCP connects (no credentials). Activity is mapped into lanes
so the console shows Wazuh / Suricata / Zeek / TheHive / Shuffle / … as living
streams — not a flat generic log list.
"""

from __future__ import annotations

import logging
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.core.config import get_infra_settings
from app.db.session import fetch_all, fetch_one
from app.services.soc_agent_client import soc_agent_enabled

logger = logging.getLogger(__name__)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _host_port_from_url(url: str, default_port: int) -> Tuple[str, int]:
    try:
        p = urlparse(url if "://" in url else f"http://{url}")
        host = p.hostname or url
        port = int(p.port or default_port)
        return host, port
    except Exception:  # noqa: BLE001
        return url, default_port


def _tcp_probe(host: str, port: int, timeout: float = 0.45) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            ms = int((time.monotonic() - started) * 1000)
            return {"reachable": True, "latency_ms": ms, "error": None}
    except OSError as exc:
        return {"reachable": False, "latency_ms": None, "error": str(exc)[:120]}


def engine_catalog() -> List[Dict[str, Any]]:
    """Canonical MSSP stack lanes (lab defaults; overridable via env)."""
    infra = get_infra_settings()
    wazuh_host, wazuh_port = _host_port_from_url(infra.wazuh_api_url, 55000)
    thehive_host, thehive_port = _host_port_from_url(infra.thehive_url, 9000)
    shuffle_host = infra.shuffle_host
    suricata_host = infra.suricata_host
    greenbone_host = infra.greenbone_host
    misp_host = _env("MISP_HOST", "192.168.0.218")
    misp_url = _env("MISP_URL", f"http://{misp_host}:8080")
    misp_h, misp_p = _host_port_from_url(misp_url, 8080)
    velo_host = _env("VELOCIRAPTOR_HOST", "192.168.0.220")
    velo_url = _env("VELOCIRAPTOR_SERVER_URL", f"https://{velo_host}:8000")
    velo_h, velo_p = _host_port_from_url(velo_url, 8000)
    edge_host = _env("SECURE_EDGE_HOST", "192.168.0.217")
    soc_agent_host = _env("SOC_AGENT_HOST", "192.168.0.228")
    soc_agent_port = int(_env("SOC_AGENT_PORT", "8443") or "8443")

    return [
        {
            "id": "control_plane",
            "label": "Control Plane",
            "tool": "FastAPI · Postgres · Redis",
            "vm": "VM 100",
            "hostname": "mssp-control",
            "host": infra.control_plane_host,
            "port": 8000,
            "os": "Ubuntu",
            "lane": "control_plane",
            "sources": ["control_plane", "postgres", "redis", "portal", "audit"],
        },
        {
            "id": "wazuh",
            "label": "Wazuh Manager",
            "tool": "Wazuh · Indexer · Dashboard",
            "vm": "VM 101",
            "hostname": "wazuh-stack",
            "host": wazuh_host,
            "port": wazuh_port,
            "os": "Ubuntu",
            "lane": "wazuh",
            "sources": ["wazuh", "edr", "syscheck", "fim"],
        },
        {
            "id": "thehive",
            "label": "TheHive",
            "tool": "Case management",
            "vm": "VM 102",
            "hostname": "thehiveshuffle",
            "host": thehive_host,
            "port": thehive_port,
            "os": "Ubuntu",
            "lane": "thehive",
            "sources": ["thehive", "case"],
        },
        {
            "id": "shuffle",
            "label": "Shuffle SOAR",
            "tool": "Playbooks / webhooks",
            "vm": "VM 102",
            "hostname": "thehiveshuffle",
            "host": shuffle_host,
            "port": 3001,
            "os": "Ubuntu",
            "lane": "shuffle",
            "sources": ["shuffle", "soar"],
        },
        {
            "id": "suricata",
            "label": "Suricata NDR",
            "tool": "IDS / IPS sensor",
            "vm": "VM 106",
            "hostname": "suricata-sensor",
            "host": suricata_host,
            "port": 22,
            "os": "Ubuntu",
            "lane": "suricata",
            "sources": ["suricata"],
        },
        {
            "id": "zeek",
            "label": "Zeek NDR",
            "tool": "Network telemetry",
            "vm": "VM 106",
            "hostname": "suricata-sensor",
            "host": suricata_host,
            "port": 22,
            "os": "Ubuntu",
            "lane": "zeek",
            "sources": ["zeek", "ndr"],
        },
        {
            "id": "misp",
            "label": "MISP / Threat Intel",
            "tool": "IOC bridge",
            "vm": "VM 108",
            "hostname": "misp",
            "host": misp_h,
            "port": misp_p,
            "os": "Ubuntu",
            "lane": "misp",
            "sources": ["misp", "threat_intel"],
        },
        {
            "id": "greenbone",
            "label": "Vuln / EASM",
            "tool": "Greenbone · Nuclei · Vuls",
            "vm": "VM 109",
            "hostname": "greenbone",
            "host": greenbone_host,
            "port": 22,
            "os": "Ubuntu",
            "lane": "greenbone",
            "sources": ["greenbone", "nuclei", "vuls", "amass", "openvas"],
        },
        {
            "id": "velociraptor",
            "label": "Velociraptor",
            "tool": "DFIR / endpoint hunt",
            "vm": "VM 110",
            "hostname": "velociraptor",
            "host": velo_h,
            "port": velo_p,
            "os": "Ubuntu",
            "lane": "velociraptor",
            "sources": ["velociraptor", "dfir"],
        },
        {
            "id": "secure_edge",
            "label": "Secure Edge",
            "tool": "WAF / perimeter",
            "vm": "VM 116",
            "hostname": "secure-edge",
            "host": edge_host,
            "port": 9080,
            "os": "Ubuntu",
            "lane": "secure_edge",
            "sources": ["secure_edge", "edge"],
        },
        {
            "id": "soc_agent",
            "label": "SOC Agent",
            "tool": "Cursor deep triage",
            "vm": "VM 117",
            "hostname": "mssp-soc-agent",
            "host": soc_agent_host,
            "port": soc_agent_port,
            "os": "Ubuntu",
            "lane": "soc_agent",
            "sources": ["soc_agent", "ai_triage", "cursor"],
        },
        {
            "id": "appliances",
            "label": "Customer Appliances",
            "tool": "Edge forwarders",
            "vm": "fleet",
            "hostname": "appliances",
            "host": infra.control_plane_host,
            "port": 8000,
            "os": "Ubuntu",
            "lane": "appliances",
            "sources": ["appliance", "heartbeat"],
            "skip_probe": True,
        },
    ]


def resolve_lane(source_tool: Optional[str], category: Optional[str] = None, kind: Optional[str] = None) -> str:
    raw = f"{source_tool or ''} {category or ''} {kind or ''}".lower()
    catalog = engine_catalog()
    for eng in catalog:
        for src in eng.get("sources") or []:
            if src and src in raw:
                return str(eng["lane"])
    if "incident" in raw:
        return "thehive"
    if "notify" in raw or "notification" in raw:
        return "control_plane"
    if "portal" in raw or "audit" in raw:
        return "control_plane"
    if "alert" in raw:
        return "wazuh"
    return "control_plane"


def _probe_all(catalog: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    work = [(e["id"], e["host"], int(e["port"])) for e in catalog if not e.get("skip_probe")]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(_tcp_probe, h, p): eid for eid, h, p in work}
        for fut in as_completed(futs):
            eid = futs[fut]
            try:
                results[eid] = fut.result()
            except Exception as exc:  # noqa: BLE001
                results[eid] = {"reachable": False, "latency_ms": None, "error": str(exc)[:120]}
    # Appliances: derived from DB
    row = fetch_one(
        """
        SELECT
          (SELECT COUNT(*)::int FROM appliances WHERE status = 'online') AS online,
          (SELECT COUNT(*)::int FROM appliance_heartbeats
             WHERE heartbeat_at > now() - interval '15 minutes') AS hb
        """
    ) or {}
    online = int(row.get("online") or 0)
    results["appliances"] = {
        "reachable": online > 0,
        "latency_ms": None,
        "error": None if online > 0 else "no appliances online",
        "online": online,
        "heartbeats_15m": int(row.get("hb") or 0),
    }
    if not soc_agent_enabled():
        cur = results.get("soc_agent") or {}
        if not cur.get("reachable"):
            results["soc_agent"] = {
                **cur,
                "reachable": False,
                "error": cur.get("error") or "SOC_AGENT_ENABLED off",
            }
    return results


def _recent_by_lane(limit_per: int = 18) -> Dict[str, List[Dict[str, Any]]]:
    """Pull recent signals and bucket into engine lanes (per-source so Wazuh cannot drown others)."""
    buckets: Dict[str, List[Dict[str, Any]]] = {}

    def add(lane: str, item: Dict[str, Any]) -> None:
        buckets.setdefault(lane, []).append(item)

    # Per-engine alert pulls — keeps Suricata/Zeek/Edge visible beside high-volume Wazuh
    for eng in engine_catalog():
        srcs = [s for s in (eng.get("sources") or []) if s]
        if not srcs:
            continue
        if eng["lane"] in ("control_plane", "appliances", "thehive", "soc_agent"):
            continue
        alerts = fetch_all(
            """
            SELECT id::text AS id, alert_title AS title, severity, status, source_tool,
                   destination_host,
                   (created_at AT TIME ZONE 'utc')::text AS ts
            FROM security_alerts
            WHERE lower(coalesce(source_tool, '')) = ANY(%s)
            ORDER BY created_at DESC
            LIMIT %s;
            """,
            (srcs, limit_per),
        )
        for a in alerts or []:
            lane = str(eng["lane"])
            add(
                lane,
                {
                    "id": f"alert-{a['id']}",
                    "lane": lane,
                    "kind": "alert",
                    "severity": (a.get("severity") or "info").lower(),
                    "title": a.get("title") or "Alert",
                    "detail": f"{a.get('source_tool')} · {a.get('destination_host') or '—'} · {a.get('status')}",
                    "ts": a.get("ts"),
                    "alert_id": a["id"],
                },
            )

    incidents = fetch_all(
        """
        SELECT id::text AS id, incident_number, title, severity, status,
               (created_at AT TIME ZONE 'utc')::text AS ts
        FROM incidents
        ORDER BY created_at DESC
        LIMIT 40;
        """
    )
    for i in incidents or []:
        add(
            "thehive",
            {
                "id": f"inc-{i['id']}",
                "lane": "thehive",
                "kind": "incident",
                "severity": (i.get("severity") or "medium").lower(),
                "title": f"{i.get('incident_number')}: {i.get('title')}",
                "detail": f"status={i.get('status')}",
                "ts": i.get("ts"),
                "incident_id": i["id"],
            },
        )

    edge = fetch_all(
        """
        SELECT id::text AS id, event_type, severity, summary, public_hostname,
               (created_at AT TIME ZONE 'utc')::text AS ts
        FROM secure_edge_events
        ORDER BY created_at DESC
        LIMIT 40;
        """
    )
    for e in edge or []:
        add(
            "secure_edge",
            {
                "id": f"edge-{e['id']}",
                "lane": "secure_edge",
                "kind": "edge",
                "severity": (e.get("severity") or "info").lower(),
                "title": f"{e.get('event_type')}: {e.get('summary') or ''}",
                "detail": e.get("public_hostname") or "edge",
                "ts": e.get("ts"),
            },
        )

    ai = fetch_all(
        """
        SELECT id::text AS id, alert_title AS title, severity, ai_verdict,
               (coalesce(ai_triaged_at, updated_at) AT TIME ZONE 'utc')::text AS ts
        FROM security_alerts
        WHERE ai_verdict IS NOT NULL
        ORDER BY coalesce(ai_triaged_at, updated_at) DESC
        LIMIT 30;
        """
    )
    for a in ai or []:
        add(
            "soc_agent",
            {
                "id": f"ai-{a['id']}",
                "lane": "soc_agent",
                "kind": "ai_triage",
                "severity": (a.get("severity") or "info").lower(),
                "title": f"AI · {a.get('ai_verdict')}",
                "detail": a.get("title") or "",
                "ts": a.get("ts"),
                "alert_id": a["id"],
            },
        )

    # One latest heartbeat per appliance — avoid flood
    hbs = fetch_all(
        """
        SELECT DISTINCT ON (a.id)
               h.id::text AS id, a.appliance_name, h.health_status, a.status,
               (h.heartbeat_at AT TIME ZONE 'utc')::text AS ts
        FROM appliance_heartbeats h
        JOIN appliances a ON a.id = h.appliance_id
        ORDER BY a.id, h.heartbeat_at DESC
        LIMIT 20;
        """
    )
    for h in hbs or []:
        add(
            "appliances",
            {
                "id": f"hb-{h['id']}",
                "lane": "appliances",
                "kind": "heartbeat",
                "severity": "info",
                "title": f"HB · {h.get('appliance_name')}",
                "detail": f"{h.get('health_status')} · {h.get('status')}",
                "ts": h.get("ts"),
            },
        )

    audits = fetch_all(
        """
        SELECT id::text AS id, action, entity_type,
               (created_at AT TIME ZONE 'utc')::text AS ts
        FROM audit_logs
        ORDER BY created_at DESC
        LIMIT 25;
        """
    )
    for a in audits or []:
        add(
            "control_plane",
            {
                "id": f"audit-{a['id']}",
                "lane": "control_plane",
                "kind": "portal",
                "severity": "info",
                "title": f"Portal · {a.get('action')}",
                "detail": f"entity={a.get('entity_type')}",
                "ts": a.get("ts"),
            },
        )

    # Trim + sort each lane
    for lane, items in list(buckets.items()):
        items.sort(key=lambda x: str(x.get("ts") or ""), reverse=True)
        buckets[lane] = items[:limit_per]
    return buckets


def build_engine_wall() -> Dict[str, Any]:
    catalog = engine_catalog()
    probes = _probe_all(catalog)
    streams = _recent_by_lane(16)

    tool_counts = fetch_all(
        """
        SELECT lower(coalesce(nullif(trim(source_tool), ''), 'unknown')) AS tool,
               COUNT(*)::int AS n
        FROM security_alerts
        WHERE created_at > now() - interval '24 hours'
        GROUP BY 1;
        """
    )
    by_tool = {str(r["tool"]): int(r["n"]) for r in (tool_counts or [])}

    lanes: List[Dict[str, Any]] = []
    for eng in catalog:
        probe = probes.get(eng["id"]) or {"reachable": False}
        srcs = eng.get("sources") or []
        pulse = sum(int(by_tool.get(s, 0)) for s in srcs)
        stream = streams.get(eng["lane"]) or []
        status = "online" if probe.get("reachable") else "offline"
        if eng["id"] == "appliances":
            status = "online" if probe.get("reachable") else "idle"
        lanes.append(
            {
                **eng,
                "status": status,
                "reachable": bool(probe.get("reachable")),
                "latency_ms": probe.get("latency_ms"),
                "probe_error": probe.get("error"),
                "pulse_24h": pulse,
                "stream": stream,
                "stream_count": len(stream),
            }
        )

    online = sum(1 for L in lanes if L.get("reachable"))
    return {
        "generated_at": _utc_now(),
        "summary": {
            "engines_total": len(lanes),
            "engines_online": online,
            "engines_offline": len(lanes) - online,
        },
        "lanes": lanes,
    }
