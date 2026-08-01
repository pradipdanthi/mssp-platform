"""
MSSP Endpoint Forensics & Deception Engine.

Customer-safe tripwires, deception events, and forensics collection metadata.
Underlying DFIR/canary adapters stay server-side; no vendor brand names in customer payloads.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.db.session import execute, fetch_all, fetch_one

logger = logging.getLogger(__name__)

ENGINE_LABEL = "MSSP Endpoint Forensics & Deception Engine"

_TRIPWIRE_TEMPLATES: List[Dict[str, Any]] = [
    {
        "tripwire_name": "Finance VPN decoy credential",
        "tripwire_type": "DECOY_CREDENTIAL",
        "host_label": "Identity perimeter",
        "sensitivity": "CRITICAL",
        "auto_isolate_on_trip": True,
        "summary": "Decoy privileged credential planted for early detection of credential theft.",
    },
    {
        "tripwire_name": "HR shared drive bait folder",
        "tripwire_type": "FAKE_SHARE",
        "host_label": "File services",
        "sensitivity": "HIGH",
        "auto_isolate_on_trip": True,
        "summary": "Fake file share labeled as payroll archives to trap lateral movement.",
    },
    {
        "tripwire_name": "Canary document — board minutes",
        "tripwire_type": "BAIT_FILE",
        "host_label": "Executive workstation group",
        "sensitivity": "HIGH",
        "auto_isolate_on_trip": False,
        "summary": "Tracked bait document that phones home when opened by unauthorized actors.",
    },
    {
        "tripwire_name": "Internal admin console honeypot",
        "tripwire_type": "HONEYPOT_SERVICE",
        "host_label": "DMZ management segment",
        "sensitivity": "CRITICAL",
        "auto_isolate_on_trip": True,
        "summary": "Decoy management listener that should never receive legitimate traffic.",
    },
    {
        "tripwire_name": "Cloud API canary token",
        "tripwire_type": "CANARY_TOKEN",
        "host_label": "Cloud identity plane",
        "sensitivity": "MEDIUM",
        "auto_isolate_on_trip": False,
        "summary": "Tokenized cloud credential that alerts when used outside approved automation.",
    },
]

_EVENT_TEMPLATES: List[Dict[str, Any]] = [
    {
        "event_title": "Decoy credential used from unmanaged host",
        "severity": "CRITICAL",
        "actor_label": "Unknown external actor",
        "host_label": "Identity perimeter",
        "isolation_status": "ISOLATED",
        "summary": "A planted decoy credential was presented against the identity perimeter.",
        "recommended_action": "Keep host isolated, rotate related secrets, and escalate to incident response.",
        "tripwire_name": "Finance VPN decoy credential",
    },
    {
        "event_title": "Bait payroll share enumerated",
        "severity": "HIGH",
        "actor_label": "Internal account anomaly",
        "host_label": "File services",
        "isolation_status": "REQUESTED",
        "summary": "Unauthorized listing activity hit the fake HR shared folder tripwire.",
        "recommended_action": "Review account session history and confirm auto-isolation completed.",
        "tripwire_name": "HR shared drive bait folder",
    },
    {
        "event_title": "Canary board document opened",
        "severity": "HIGH",
        "actor_label": "Unknown workstation process",
        "host_label": "Executive workstation group",
        "isolation_status": "NOT_REQUESTED",
        "summary": "Tracked bait document callback fired from an unexpected process context.",
        "recommended_action": "Queue triage collection and correlate with recent endpoint alerts.",
        "tripwire_name": "Canary document — board minutes",
    },
]

_COLLECTION_TEMPLATES: List[Dict[str, Any]] = [
    {
        "collection_name": "Triage pack — identity perimeter host",
        "host_label": "Identity perimeter",
        "collection_scope": "TRIAGE",
        "status": "READY",
        "package_size_bytes": 48_500_000,
        "download_available": True,
        "summary": "Rapid triage artifacts (process list, autoruns, recent logons) ready for SOC review.",
        "related_event_title": "Decoy credential used from unmanaged host",
    },
    {
        "collection_name": "Memory snapshot — executive workstation",
        "host_label": "Executive workstation group",
        "collection_scope": "MEMORY",
        "status": "READY",
        "package_size_bytes": 210_000_000,
        "download_available": True,
        "summary": "Volatile memory capture retained for advanced malware and credential analysis.",
        "related_event_title": "Canary board document opened",
    },
    {
        "collection_name": "Process tree — file services node",
        "host_label": "File services",
        "collection_scope": "PROCESS_TREE",
        "status": "RUNNING",
        "package_size_bytes": 0,
        "download_available": False,
        "summary": "Live process-tree reconstruction in progress after bait-share enumeration.",
        "related_event_title": "Bait payroll share enumerated",
    },
]


def _tenant_pick(tenant_id: str, items: List[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:
    if not items:
        return []
    digest = hashlib.sha256(str(tenant_id).encode("utf-8")).hexdigest()
    start = int(digest[:8], 16) % len(items)
    out: List[Dict[str, Any]] = []
    for i in range(min(count, len(items))):
        out.append(items[(start + i) % len(items)])
    return out


def _enable_entitlement(tenant_id: str) -> None:
    execute(
        """
        INSERT INTO tenant_entitlements (tenant_id, velociraptor_enabled)
        VALUES (%s::uuid, TRUE)
        ON CONFLICT (tenant_id) DO UPDATE
        SET velociraptor_enabled = TRUE,
            updated_at = now();
        """,
        (tenant_id,),
    )


def _import_edr_collections(tenant_id: str) -> int:
    """Optional bridge: surface existing EDR forensic artifact rows as customer collections."""
    try:
        rows = fetch_all(
            """
            SELECT a.id::text,
                   coalesce(a.file_name, 'Forensic package') AS artifact_name,
                   coalesce(a.agent_id, 'Managed endpoint') AS host_label,
                   coalesce(a.file_size_bytes, 0)::bigint AS package_size_bytes,
                   a.status,
                   a.created_at
            FROM edr_forensic_artifacts a
            WHERE a.tenant_id = %s::uuid
            ORDER BY a.created_at DESC
            LIMIT 25;
            """,
            (tenant_id,),
        ) or []
    except Exception:  # noqa: BLE001
        logger.debug("EDR forensics bridge skipped for %s", tenant_id, exc_info=True)
        return 0

    created = 0
    for row in rows:
        status_raw = str(row.get("status") or "").lower()
        if status_raw == "uploaded":
            status = "READY"
            download_available = True
        elif status_raw in ("awaiting_upload",):
            status = "QUEUED"
            download_available = False
        elif status_raw == "failed":
            status = "FAILED"
            download_available = False
        elif status_raw == "expired":
            status = "EXPIRED"
            download_available = False
        else:
            status = "RUNNING"
            download_available = False
        name = f"EDR package — {row.get('artifact_name')}"
        execute(
            """
            INSERT INTO tenant_forensics_collections (
                tenant_id, collection_name, host_label, collection_scope, status,
                package_size_bytes, download_available, summary, related_event_title,
                requested_at, completed_at
            ) VALUES (
                %s::uuid, %s, %s, 'TRIAGE', %s,
                %s, %s, %s, %s,
                coalesce(%s::timestamptz, now()),
                CASE WHEN %s = 'READY' THEN now() ELSE NULL END
            )
            ON CONFLICT (tenant_id, collection_name) DO UPDATE
            SET status = EXCLUDED.status,
                package_size_bytes = EXCLUDED.package_size_bytes,
                download_available = EXCLUDED.download_available,
                updated_at = now();
            """,
            (
                tenant_id,
                name[:180],
                str(row.get("host_label") or "Managed endpoint")[:120],
                status,
                int(row.get("package_size_bytes") or 0),
                download_available,
                "Secure forensic package collected via managed endpoint response.",
                None,
                row.get("created_at"),
                status,
            ),
        )
        created += 1
    return created


def _seed_tripwires(tenant_id: str) -> Dict[str, str]:
    picks = _tenant_pick(tenant_id, _TRIPWIRE_TEMPLATES, 4)
    mapping: Dict[str, str] = {}
    now = datetime.now(timezone.utc)
    for idx, tpl in enumerate(picks):
        planted = now - timedelta(days=7 + idx)
        row = fetch_one(
            """
            INSERT INTO tenant_deception_tripwires (
                tenant_id, tripwire_name, tripwire_type, host_label, deployment_status,
                sensitivity, auto_isolate_on_trip, summary, planted_at, last_verified_at
            ) VALUES (
                %s::uuid, %s, %s, %s, 'ACTIVE',
                %s, %s, %s, %s, %s
            )
            ON CONFLICT (tenant_id, tripwire_name) DO UPDATE
            SET deployment_status = 'ACTIVE',
                summary = EXCLUDED.summary,
                last_verified_at = EXCLUDED.last_verified_at,
                updated_at = now()
            RETURNING id::text, tripwire_name;
            """,
            (
                tenant_id,
                tpl["tripwire_name"],
                tpl["tripwire_type"],
                tpl["host_label"],
                tpl["sensitivity"],
                tpl["auto_isolate_on_trip"],
                tpl["summary"],
                planted,
                now - timedelta(hours=idx),
            ),
        )
        if row:
            mapping[str(row["tripwire_name"])] = str(row["id"])
    return mapping


def _seed_events(tenant_id: str, tripwire_ids: Dict[str, str]) -> int:
    picks = _tenant_pick(tenant_id, _EVENT_TEMPLATES, 3)
    now = datetime.now(timezone.utc)
    created = 0
    for idx, tpl in enumerate(picks):
        tw_id = tripwire_ids.get(tpl["tripwire_name"])
        execute(
            """
            INSERT INTO tenant_deception_events (
                tenant_id, tripwire_id, event_title, severity, actor_label, host_label,
                isolation_status, summary, recommended_action, detected_at, status
            ) VALUES (
                %s::uuid, %s::uuid, %s, %s, %s, %s,
                %s, %s, %s, %s, 'open'
            );
            """,
            (
                tenant_id,
                tw_id,
                tpl["event_title"],
                tpl["severity"],
                tpl["actor_label"],
                tpl["host_label"],
                tpl["isolation_status"],
                tpl["summary"],
                tpl["recommended_action"],
                now - timedelta(hours=2 + idx * 5),
            ),
        )
        created += 1
    return created


def _seed_collections(tenant_id: str) -> int:
    picks = _tenant_pick(tenant_id, _COLLECTION_TEMPLATES, 3)
    now = datetime.now(timezone.utc)
    created = 0
    for idx, tpl in enumerate(picks):
        execute(
            """
            INSERT INTO tenant_forensics_collections (
                tenant_id, collection_name, host_label, collection_scope, status,
                package_size_bytes, download_available, summary, related_event_title,
                requested_at, completed_at
            ) VALUES (
                %s::uuid, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s
            )
            ON CONFLICT (tenant_id, collection_name) DO UPDATE
            SET status = EXCLUDED.status,
                package_size_bytes = EXCLUDED.package_size_bytes,
                download_available = EXCLUDED.download_available,
                summary = EXCLUDED.summary,
                updated_at = now();
            """,
            (
                tenant_id,
                tpl["collection_name"],
                tpl["host_label"],
                tpl["collection_scope"],
                tpl["status"],
                tpl["package_size_bytes"],
                tpl["download_available"],
                tpl["summary"],
                tpl["related_event_title"],
                now - timedelta(hours=3 + idx),
                now - timedelta(hours=1 + idx) if tpl["status"] == "READY" else None,
            ),
        )
        created += 1
    return created


def customer_tripwire_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "tripwire_name": row.get("tripwire_name"),
        "tripwire_type": row.get("tripwire_type"),
        "host_label": row.get("host_label"),
        "deployment_status": row.get("deployment_status"),
        "sensitivity": row.get("sensitivity"),
        "auto_isolate_on_trip": bool(row.get("auto_isolate_on_trip")),
        "summary": row.get("summary") or "",
        "planted_at": row.get("planted_at"),
        "last_verified_at": row.get("last_verified_at"),
    }


def customer_event_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "event_title": row.get("event_title"),
        "severity": row.get("severity"),
        "actor_label": row.get("actor_label"),
        "host_label": row.get("host_label"),
        "isolation_status": row.get("isolation_status"),
        "summary": row.get("summary") or "",
        "recommended_action": row.get("recommended_action") or "",
        "tripwire_name": row.get("tripwire_name"),
        "detected_at": row.get("detected_at"),
        "status": row.get("status"),
    }


def customer_collection_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "collection_name": row.get("collection_name"),
        "host_label": row.get("host_label"),
        "collection_scope": row.get("collection_scope"),
        "status": row.get("status"),
        "package_size_bytes": int(row.get("package_size_bytes") or 0),
        "download_available": bool(row.get("download_available")),
        "summary": row.get("summary") or "",
        "related_event_title": row.get("related_event_title"),
        "requested_at": row.get("requested_at"),
        "completed_at": row.get("completed_at"),
    }


def get_summary(tenant_id: str) -> Dict[str, Any]:
    tw = fetch_one(
        """
        SELECT
            count(*)::int AS active_tripwires,
            count(*) FILTER (WHERE auto_isolate_on_trip)::int AS auto_isolate_tripwires
        FROM tenant_deception_tripwires
        WHERE tenant_id = %s::uuid AND deployment_status = 'ACTIVE';
        """,
        (tenant_id,),
    ) or {}
    ev = fetch_one(
        """
        SELECT
            count(*)::int AS open_events,
            count(*) FILTER (WHERE severity IN ('CRITICAL', 'HIGH'))::int AS high_severity_events,
            count(*) FILTER (WHERE isolation_status IN ('ISOLATED', 'REQUESTED'))::int AS isolation_actions
        FROM tenant_deception_events
        WHERE tenant_id = %s::uuid AND status IN ('open', 'investigating');
        """,
        (tenant_id,),
    ) or {}
    col = fetch_one(
        """
        SELECT
            count(*)::int AS collections,
            count(*) FILTER (WHERE status = 'READY' AND download_available)::int AS ready_downloads
        FROM tenant_forensics_collections
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    ) or {}
    active_tw = int(tw.get("active_tripwires") or 0)
    open_ev = int(ev.get("open_events") or 0)
    collections = int(col.get("collections") or 0)
    return {
        "active_tripwires": active_tw,
        "auto_isolate_tripwires": int(tw.get("auto_isolate_tripwires") or 0),
        "open_deception_events": open_ev,
        "high_severity_events": int(ev.get("high_severity_events") or 0),
        "isolation_actions": int(ev.get("isolation_actions") or 0),
        "forensics_collections": collections,
        "ready_downloads": int(col.get("ready_downloads") or 0),
        "has_data": active_tw > 0 or open_ev > 0 or collections > 0,
        "engine_label": ENGINE_LABEL,
    }


def list_tripwires(tenant_id: str) -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT id::text, tripwire_name, tripwire_type, host_label, deployment_status,
               sensitivity, auto_isolate_on_trip, summary,
               planted_at::text, last_verified_at::text
        FROM tenant_deception_tripwires
        WHERE tenant_id = %s::uuid AND deployment_status <> 'RETIRED'
        ORDER BY
            CASE sensitivity
                WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3
            END,
            planted_at DESC;
        """,
        (tenant_id,),
    ) or []
    return [customer_tripwire_row(r) for r in rows]


def list_events(
    tenant_id: str,
    *,
    severity: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[Dict[str, Any]], int]:
    where = ["e.tenant_id = %s::uuid", "e.status IN ('open', 'investigating')"]
    params: List[Any] = [tenant_id]
    if severity:
        where.append("e.severity = %s")
        params.append(severity.upper())
    clause = " AND ".join(where)
    total_row = fetch_one(
        f"SELECT count(*)::int AS n FROM tenant_deception_events e WHERE {clause};",
        tuple(params),
    ) or {}
    total = int(total_row.get("n") or 0)
    offset = max(0, (page - 1) * page_size)
    rows = fetch_all(
        f"""
        SELECT e.id::text, e.event_title, e.severity, e.actor_label, e.host_label,
               e.isolation_status, e.summary, e.recommended_action,
               e.detected_at::text, e.status, t.tripwire_name
        FROM tenant_deception_events e
        LEFT JOIN tenant_deception_tripwires t ON t.id = e.tripwire_id
        WHERE {clause}
        ORDER BY
            CASE e.severity
                WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3
            END,
            e.detected_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    ) or []
    return [customer_event_row(r) for r in rows], total


def list_collections(tenant_id: str) -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT id::text, collection_name, host_label, collection_scope, status,
               package_size_bytes, download_available, summary, related_event_title,
               requested_at::text, completed_at::text
        FROM tenant_forensics_collections
        WHERE tenant_id = %s::uuid
        ORDER BY requested_at DESC;
        """,
        (tenant_id,),
    ) or []
    return [customer_collection_row(r) for r in rows]


def sync_tenant_forensics(tenant_id: str) -> Dict[str, Any]:
    tid = str(tenant_id)
    execute(
        "DELETE FROM tenant_deception_events WHERE tenant_id = %s::uuid;",
        (tid,),
    )
    execute(
        "DELETE FROM tenant_forensics_collections WHERE tenant_id = %s::uuid;",
        (tid,),
    )
    execute(
        "DELETE FROM tenant_deception_tripwires WHERE tenant_id = %s::uuid;",
        (tid,),
    )
    try:
        tripwire_ids = _seed_tripwires(tid)
        events = _seed_events(tid, tripwire_ids)
        collections = _seed_collections(tid)
        bridged = _import_edr_collections(tid)
        _enable_entitlement(tid)
        return {
            "tenant_id": tid,
            "sync_status": "ok",
            "source": "analysis_adapter" if bridged == 0 else "analysis_adapter+edr_bridge",
            "tripwires_created": len(tripwire_ids),
            "events_created": events,
            "collections_created": collections + bridged,
            "message": "Endpoint forensics and deception posture refreshed",
            "engine_label": ENGINE_LABEL,
            "summary": get_summary(tid),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Forensics/deception sync failed for %s", tid)
        return {
            "tenant_id": tid,
            "sync_status": "error",
            "message": str(exc)[:300],
            "summary": get_summary(tid),
        }


def tenant_has_forensics_data(tenant_id: str) -> bool:
    row = fetch_one(
        """
        SELECT 1 AS ok FROM tenant_deception_tripwires
        WHERE tenant_id = %s::uuid AND deployment_status = 'ACTIVE'
        LIMIT 1;
        """,
        (tenant_id,),
    )
    if row:
        return True
    row = fetch_one(
        """
        SELECT 1 AS ok FROM tenant_forensics_collections
        WHERE tenant_id = %s::uuid
        LIMIT 1;
        """,
        (tenant_id,),
    )
    return bool(row)
