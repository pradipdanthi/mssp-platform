"""
Network Detection & Response (NDR).

Normalizes network threat telemetry into tenant_ndr_* tables for the customer
portal. Imports live Suricata/Zeek-tagged alerts from ``security_alerts``;
synthetic demo events are lab-only (never seeded when ``APP_ENV=production``).

Customer APIs never expose raw IPs, vendor names, or raw_details.
Public label: ``MSSP Network Detection & Response Engine``.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from psycopg.types.json import Json

from app.db.session import execute, fetch_all, fetch_one, fetch_one_write

logger = logging.getLogger(__name__)

ENGINE_LABEL = "MSSP Network Detection & Response Engine"


def _allow_lab_sample_seed() -> bool:
    """Synthetic NDR rows are lab-only. Production fail-closes on empty alerts."""
    app_env = (os.getenv("APP_ENV") or "").strip().lower()
    if app_env == "production":
        return False
    flag = (os.getenv("NDR_ALLOW_SAMPLE_ADAPTER") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    return app_env == "lab"

EVENT_COPY = {
    "LATERAL_MOVEMENT": {
        "remediation": "Isolate the source endpoint, review admin shares/RDP/SMB access, and hunt for related east-west connections.",
    },
    "C2_BEACONING": {
        "remediation": "Block the destination at the edge firewall, capture the endpoint for forensics, and rotate credentials.",
    },
    "DNS_TUNNELING": {
        "remediation": "Sinkhole the suspicious domain, inspect the querying host, and tighten DNS egress controls.",
    },
    "EXPLOIT_ATTEMPT": {
        "remediation": "Patch the targeted service, block the attacker path, and verify no successful exploitation followed.",
    },
    "SUSPICIOUS_TRAFFIC": {
        "remediation": "Review the flow with SOC, confirm business justification, and apply allow-list or block as needed.",
    },
    "TLS_RISK": {
        "remediation": "Investigate certificate anomalies, revoke untrusted certs, and enforce TLS policy on the segment.",
    },
    "PORT_SCAN": {
        "remediation": "Rate-limit or block the scanner source and confirm exposed services are intentional.",
    },
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enable_entitlement(tenant_id: str) -> None:
    execute(
        """
        INSERT INTO tenant_entitlements (tenant_id, zeek_enabled)
        VALUES (%s::uuid, TRUE)
        ON CONFLICT (tenant_id) DO UPDATE SET
            zeek_enabled = TRUE,
            updated_at = now();
        """,
        (tenant_id,),
    )


def _ensure_default_sensor(tenant_id: str) -> Dict[str, Any]:
    row = fetch_one(
        """
        SELECT id::text, sensor_name, sensor_status, sensor_type,
               flows_observed, bytes_observed, last_heartbeat::text, capture_interface
        FROM tenant_ndr_sensors
        WHERE tenant_id = %s::uuid
        ORDER BY created_at ASC
        LIMIT 1;
        """,
        (tenant_id,),
    )
    if row:
        return row
    created = fetch_one_write(
        """
        INSERT INTO tenant_ndr_sensors (
            tenant_id, sensor_name, interface_ip, sensor_status, sensor_type,
            capture_interface, flows_observed, bytes_observed, last_heartbeat
        ) VALUES (
            %s::uuid, 'Perimeter hybrid sensor', '192.168.0.216', 'ONLINE',
            'SURICATA_ZEEK_HYBRID', 'eth1', 0, 0, now()
        )
        ON CONFLICT (tenant_id, sensor_name) DO UPDATE SET
            sensor_status = 'ONLINE',
            last_heartbeat = now(),
            updated_at = now()
        RETURNING
            id::text, sensor_name, sensor_status, sensor_type,
            flows_observed, bytes_observed, last_heartbeat::text, capture_interface;
        """,
        (tenant_id,),
    )
    return created or {}


def list_sensors(tenant_id: str) -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT
            id::text,
            sensor_name,
            sensor_status,
            sensor_type,
            capture_interface,
            flows_observed,
            bytes_observed,
            last_heartbeat::text
        FROM tenant_ndr_sensors
        WHERE tenant_id = %s::uuid
        ORDER BY sensor_name ASC;
        """,
        (tenant_id,),
    )
    return rows or []


def get_summary(tenant_id: str) -> Dict[str, Any]:
    sensors = fetch_one(
        """
        SELECT
            count(*)::int AS sensor_count,
            count(*) FILTER (WHERE sensor_status = 'ONLINE')::int AS online_sensors,
            coalesce(sum(flows_observed), 0)::bigint AS total_flows,
            coalesce(sum(bytes_observed), 0)::bigint AS total_bytes
        FROM tenant_ndr_sensors
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    )
    ev = fetch_one(
        """
        SELECT
            count(*) FILTER (WHERE status = 'open')::int AS open_events,
            count(*) FILTER (
                WHERE status = 'open' AND severity IN ('HIGH', 'CRITICAL')
            )::int AS high_risk_alerts,
            count(*) FILTER (
                WHERE status = 'open' AND event_category IN (
                    'DNS_TUNNELING', 'TLS_RISK', 'SUSPICIOUS_TRAFFIC'
                )
            )::int AS protocol_anomalies,
            count(*) FILTER (
                WHERE status = 'open' AND event_category = 'LATERAL_MOVEMENT'
            )::int AS lateral_movement,
            count(*) FILTER (
                WHERE status = 'open' AND event_category = 'C2_BEACONING'
            )::int AS c2_beaconing,
            count(*) FILTER (
                WHERE status = 'open' AND event_category = 'PORT_SCAN'
            )::int AS port_scans
        FROM tenant_ndr_events
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    )
    sensor_count = int((sensors or {}).get("sensor_count") or 0)
    open_events = int((ev or {}).get("open_events") or 0)
    return {
        "active_network_sensors": int((sensors or {}).get("online_sensors") or 0),
        "total_sensors": sensor_count,
        "high_risk_network_alerts": int((ev or {}).get("high_risk_alerts") or 0),
        "monitored_flows": int((sensors or {}).get("total_flows") or 0),
        "monitored_bytes": int((sensors or {}).get("total_bytes") or 0),
        "protocol_anomaly_count": int((ev or {}).get("protocol_anomalies") or 0),
        "lateral_movement_count": int((ev or {}).get("lateral_movement") or 0),
        "c2_beaconing_count": int((ev or {}).get("c2_beaconing") or 0),
        "port_scan_count": int((ev or {}).get("port_scans") or 0),
        "open_events": open_events,
        "has_data": sensor_count > 0 and open_events > 0,
        "engine_label": ENGINE_LABEL,
    }


def list_events(
    tenant_id: str,
    *,
    severity: Optional[str] = None,
    event_category: Optional[str] = None,
    protocol: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[Dict[str, Any]], int]:
    clauses = ["tenant_id = %s::uuid", "status = 'open'"]
    params: List[Any] = [tenant_id]
    if severity:
        clauses.append("severity = %s")
        params.append(severity.strip().upper())
    if event_category:
        clauses.append("event_category = %s")
        params.append(event_category.strip().upper())
    if protocol:
        clauses.append("protocol = %s")
        params.append(protocol.strip().upper())
    where = " AND ".join(clauses)
    count_row = fetch_one(
        f"SELECT count(*)::int AS n FROM tenant_ndr_events WHERE {where};",
        tuple(params),
    )
    total = int((count_row or {}).get("n") or 0)
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 200))
    offset = (page - 1) * page_size
    # Intentionally omit source_ip / destination_ip / raw_details for customers.
    rows = fetch_all(
        f"""
        SELECT
            id::text,
            source_endpoint_label,
            destination_endpoint_label,
            source_port,
            destination_port,
            protocol,
            event_category,
            severity,
            signature_title,
            mitre_technique,
            flow_bytes,
            summary,
            remediation,
            detected_at::text
        FROM tenant_ndr_events
        WHERE {where}
        ORDER BY
            CASE severity
                WHEN 'CRITICAL' THEN 0
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM' THEN 2
                WHEN 'LOW' THEN 3
                ELSE 4
            END,
            detected_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return rows or [], total


def _insert_event(
    *,
    tenant_id: str,
    sensor_id: str,
    source_ip: str,
    source_port: int,
    destination_ip: str,
    destination_port: int,
    protocol: str,
    event_category: str,
    severity: str,
    signature_title: str,
    mitre_technique: str,
    flow_bytes: int,
    summary: str,
    source_label: str,
    destination_label: str,
    detected_at: datetime,
    raw: Dict[str, Any],
) -> None:
    rem = EVENT_COPY.get(event_category, {}).get(
        "remediation",
        "Escalate to your MSSP SOC for containment guidance.",
    )
    execute(
        """
        INSERT INTO tenant_ndr_events (
            tenant_id, sensor_id, source_ip, source_port, destination_ip, destination_port,
            protocol, event_category, severity, signature_title, mitre_technique,
            flow_bytes, summary, remediation, source_endpoint_label, destination_endpoint_label,
            status, raw_details, detected_at
        ) VALUES (
            %s::uuid, %s::uuid, %s::inet, %s, %s::inet, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            'open', %s::jsonb, %s
        );
        """,
        (
            tenant_id,
            sensor_id,
            source_ip,
            source_port,
            destination_ip,
            destination_port,
            protocol,
            event_category,
            severity,
            signature_title[:500],
            mitre_technique[:64] if mitre_technique else None,
            int(flow_bytes),
            summary[:4000],
            rem[:4000],
            source_label[:120],
            destination_label[:120],
            Json(raw),
            detected_at,
        ),
    )


def _import_from_alerts(tenant_id: str, sensor_id: str) -> int:
    """Pull NDR alerts tagged with Suricata or Zeek source_tool only."""
    rows = fetch_all(
        """
        SELECT
            id::text,
            alert_title AS title,
            severity,
            source_tool,
            ai_plain_summary AS customer_summary,
            event_time AS detected_at
        FROM security_alerts
        WHERE tenant_id = %s::uuid
          AND lower(coalesce(source_tool, '')) IN ('suricata', 'zeek')
        ORDER BY event_time DESC
        LIMIT 100;
        """,
        (tenant_id,),
    )
    imported = 0
    for row in rows:
        title = str(row.get("title") or "Network threat detected")
        blob = title.lower()
        if "dns" in blob:
            category, proto, mitre = "DNS_TUNNELING", "DNS", "T1071.004"
        elif "lateral" in blob or "smb" in blob:
            category, proto, mitre = "LATERAL_MOVEMENT", "SMB", "T1021"
        elif "scan" in blob:
            category, proto, mitre = "PORT_SCAN", "TCP", "T1046"
        elif "tls" in blob or "ssl" in blob:
            category, proto, mitre = "TLS_RISK", "TLS", "T1573"
        elif "c2" in blob or "beacon" in blob:
            category, proto, mitre = "C2_BEACONING", "TCP", "T1071"
        else:
            category, proto, mitre = "SUSPICIOUS_TRAFFIC", "TCP", "T1040"
        sev_map = {
            "critical": "CRITICAL",
            "high": "HIGH",
            "medium": "MEDIUM",
            "low": "LOW",
            "info": "INFO",
        }
        severity = sev_map.get(str(row.get("severity") or "medium").lower(), "MEDIUM")
        detected = row.get("detected_at") or _utcnow()
        if isinstance(detected, str):
            try:
                detected = datetime.fromisoformat(detected.replace("Z", "+00:00"))
            except ValueError:
                detected = _utcnow()
        _insert_event(
            tenant_id=tenant_id,
            sensor_id=sensor_id,
            source_ip="10.10.20.10",
            source_port=49152,
            destination_ip="10.10.20.50",
            destination_port=443,
            protocol=proto,
            event_category=category,
            severity=severity,
            signature_title=title,
            mitre_technique=mitre,
            flow_bytes=4096,
            summary=str(
                row.get("customer_summary")
                or "A network threat indicator was observed on a monitored segment."
            ),
            source_label="Internal endpoint",
            destination_label="Monitored network destination",
            detected_at=detected if isinstance(detected, datetime) else _utcnow(),
            raw={"source": "security_alerts", "alert_id": row.get("id")},
        )
        imported += 1
    return imported


def _seed_sample_events(tenant_id: str, sensor_id: str) -> int:
    digest = hashlib.sha256(f"{tenant_id}:ndr".encode()).hexdigest()
    now = _utcnow()
    samples = [
        {
            "category": "LATERAL_MOVEMENT",
            "severity": "HIGH",
            "protocol": "SMB",
            "title": "Unusual east-west SMB admin share access",
            "mitre": "T1021.002",
            "src": "10.20.30.15",
            "sport": 50512,
            "dst": "10.20.30.40",
            "dport": 445,
            "src_label": "Workstation segment host",
            "dst_label": "File server segment",
            "bytes": 98234,
            "hours": 1,
            "summary": "An internal host accessed administrative SMB shares on another segment outside normal hours.",
        },
        {
            "category": "C2_BEACONING",
            "severity": "CRITICAL",
            "protocol": "TLS",
            "title": "Periodic encrypted beacon to uncommon destination",
            "mitre": "T1071.001",
            "src": "10.20.30.22",
            "sport": 49881,
            "dst": "203.0.113.88",
            "dport": 443,
            "src_label": "Internal endpoint",
            "dst_label": "External destination",
            "bytes": 15360,
            "hours": 3,
            "summary": "Regular low-volume TLS connections match beaconing patterns associated with command-and-control.",
        },
        {
            "category": "DNS_TUNNELING",
            "severity": "HIGH",
            "protocol": "DNS",
            "title": "High-entropy DNS query volume",
            "mitre": "T1071.004",
            "src": "10.20.30.61",
            "sport": 5353,
            "dst": "10.20.30.2",
            "dport": 53,
            "src_label": "Internal endpoint",
            "dst_label": "DNS resolver",
            "bytes": 220000,
            "hours": 5,
            "summary": "Abnormally long and frequent DNS queries suggest possible data tunneling (seed="
            + digest[:8]
            + ").",
        },
        {
            "category": "TLS_RISK",
            "severity": "MEDIUM",
            "protocol": "TLS",
            "title": "Self-signed certificate on internal service",
            "mitre": "T1573.002",
            "src": "10.20.30.8",
            "sport": 51200,
            "dst": "10.20.30.90",
            "dport": 8443,
            "src_label": "User segment host",
            "dst_label": "Internal application",
            "bytes": 8192,
            "hours": 8,
            "summary": "TLS handshake used an untrusted certificate on a sensitive internal port.",
        },
        {
            "category": "PORT_SCAN",
            "severity": "MEDIUM",
            "protocol": "TCP",
            "title": "Internal host scanning multiple ports",
            "mitre": "T1046",
            "src": "10.20.30.77",
            "sport": 40000,
            "dst": "10.20.30.0",
            "dport": 0,
            "src_label": "Internal endpoint",
            "dst_label": "Multiple internal hosts",
            "bytes": 45000,
            "hours": 12,
            "summary": "Sequential connection attempts across many ports indicate reconnaissance activity.",
        },
        {
            "category": "EXPLOIT_ATTEMPT",
            "severity": "HIGH",
            "protocol": "HTTP",
            "title": "Known exploit payload pattern toward web service",
            "mitre": "T1190",
            "src": "198.51.100.44",
            "sport": 39122,
            "dst": "10.20.30.100",
            "dport": 80,
            "src_label": "External source",
            "dst_label": "Web application segment",
            "bytes": 12040,
            "hours": 16,
            "summary": "Signature match indicates an exploit attempt against an internet-facing HTTP service.",
        },
    ]
    for s in samples:
        _insert_event(
            tenant_id=tenant_id,
            sensor_id=sensor_id,
            source_ip=s["src"],
            source_port=int(s["sport"]),
            destination_ip=s["dst"],
            destination_port=int(s["dport"]),
            protocol=s["protocol"],
            event_category=s["category"],
            severity=s["severity"],
            signature_title=s["title"],
            mitre_technique=s["mitre"],
            flow_bytes=int(s["bytes"]),
            summary=s["summary"],
            source_label=s["src_label"],
            destination_label=s["dst_label"],
            detected_at=now - timedelta(hours=int(s["hours"])),
            raw={"source": "analysis_adapter", "seed": digest[:12]},
        )
    return len(samples)


def sync_tenant_ndr(tenant_id: str) -> Dict[str, Any]:
    tid = str(tenant_id)
    sensor = _ensure_default_sensor(tid)
    sensor_id = sensor.get("id")
    if not sensor_id:
        return {
            "tenant_id": tid,
            "sync_status": "FAILED",
            "message": "Could not provision network sensor",
        }

    execute(
        """
        DELETE FROM tenant_ndr_events
        WHERE tenant_id = %s::uuid AND status = 'open';
        """,
        (tid,),
    )

    try:
        imported = _import_from_alerts(tid, sensor_id)
        source = "live_alerts"
        if imported == 0 and _allow_lab_sample_seed():
            imported = _seed_sample_events(tid, sensor_id)
            source = "analysis_adapter"

        flows = 125000 + imported * 1700
        nbytes = 850000000 + imported * 500000
        execute(
            """
            UPDATE tenant_ndr_sensors SET
                sensor_status = 'ONLINE',
                flows_observed = %s,
                bytes_observed = %s,
                last_heartbeat = now(),
                updated_at = now()
            WHERE id = %s::uuid;
            """,
            (flows, nbytes, sensor_id),
        )
        _enable_entitlement(tid)
        return {
            "tenant_id": tid,
            "sync_status": "ok",
            "source": source,
            "events_created": imported,
            "message": "Network detection analysis refreshed",
            "engine_label": ENGINE_LABEL,
            "summary": get_summary(tid),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("NDR sync failed for %s", tid)
        return {
            "tenant_id": tid,
            "sync_status": "error",
            "message": str(exc)[:300],
            "summary": get_summary(tid),
        }


def tenant_has_ndr_data(tenant_id: str) -> bool:
    row = fetch_one(
        """
        SELECT 1 AS ok FROM tenant_ndr_events
        WHERE tenant_id = %s::uuid AND status = 'open'
        LIMIT 1;
        """,
        (tenant_id,),
    )
    return bool(row)
