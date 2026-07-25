"""KB-061: persist normalized SOC alerts/incidents for dashboard visibility."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from app.db.session import db_transaction
from app.schemas.soc_sync import SocSyncRequest


class TenantNotFoundError(Exception):
    pass


def _should_create_incident(payload: SocSyncRequest) -> bool:
    if payload.create_incident is not None:
        return payload.create_incident
    return payload.severity in ("high", "critical")


def _next_incident_number(cur: Any, short_code: str) -> str:
    prefix = f"INC-{short_code}-TH-"
    cur.execute(
        """
        SELECT incident_number
        FROM incidents
        WHERE incident_number LIKE %s
        ORDER BY incident_number DESC
        LIMIT 1;
        """,
        (prefix + "%",),
    )
    row = cur.fetchone()
    if not row:
        return f"{prefix}0001"
    last = row["incident_number"] if isinstance(row, dict) else row[0]
    suffix = last.rsplit("-", 1)[-1]
    try:
        n = int(suffix) + 1
    except ValueError:
        n = int(secrets.randbelow(9000) + 1000)
    return f"{prefix}{n:04d}"



def _create_incident(
    cur: Any,
    *,
    tenant_id: str,
    short_code: str,
    alert_id: str,
    payload: SocSyncRequest,
) -> Tuple[str, str]:
    incident_number = _next_incident_number(cur, short_code)
    summary = payload.customer_visible_summary or (
        f"Security incident under review: {payload.alert_title}"
    )
    impact = payload.business_impact or (
        "Our SOC is investigating. Customer-visible details will appear when approved."
    )
    cur.execute(
        """
        INSERT INTO incidents (
            tenant_id, primary_alert_id, incident_number, title,
            severity, status, customer_visible_summary, business_impact,
            internal_notes
        )
        VALUES (
            %s, %s::uuid, %s, %s,
            %s, 'open', %s, %s,
            %s
        )
        RETURNING id::text AS id, incident_number;
        """,
        (
            tenant_id,
            alert_id,
            incident_number,
            payload.alert_title,
            payload.severity,
            summary,
            impact,
            f"Synced from {payload.source_tool}:{payload.external_alert_id}",
        ),
    )
    inc = cur.fetchone()
    cur.execute(
        """
        INSERT INTO incident_alerts (incident_id, alert_id)
        VALUES (%s::uuid, %s::uuid)
        ON CONFLICT DO NOTHING;
        """,
        (inc["id"], alert_id),
    )
    cur.execute(
        """
        INSERT INTO incident_timeline (
            incident_id, event_type, visibility, title, details
        )
        VALUES (
            %s::uuid, 'created', 'internal',
            'Incident created from SOC sync',
            %s
        );
        """,
        (
            inc["id"],
            f"source_tool={payload.source_tool} external_alert_id={payload.external_alert_id}",
        ),
    )
    cur.execute(
        """
        UPDATE security_alerts
        SET status = 'incident_created',
            severity = %s,
            updated_at = now()
        WHERE id = %s::uuid;
        """,
        (payload.severity, alert_id),
    )
    return inc["id"], inc["incident_number"]


def sync_soc_alert(payload: SocSyncRequest) -> Tuple[Dict[str, Any], bool]:
    """
    Insert or return existing security_alerts row; optionally create incident.

    Always customer_visible=false. Dedup key: tenant + source_tool + external_alert_id.
    """
    with db_transaction() as cur:
        cur.execute(
            """
            SELECT id::text AS id, short_code
            FROM tenants
            WHERE short_code = %s
              AND status = 'active'
            LIMIT 1;
            """,
            (payload.tenant_short_code.upper(),),
        )
        tenant = cur.fetchone()
        if not tenant:
            raise TenantNotFoundError(payload.tenant_short_code)

        tenant_id = tenant["id"]
        short_code = tenant["short_code"]
        duplicate_key = f"soc-sync:{tenant_id}:{payload.source_tool}:{payload.external_alert_id}"
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0));", (duplicate_key,))

        cur.execute(
            """
            SELECT id::text AS id, customer_visible, status
            FROM security_alerts
            WHERE tenant_id = %s
              AND source_tool = %s
              AND external_alert_id = %s
            ORDER BY created_at
            LIMIT 1;
            """,
            (tenant_id, payload.source_tool, payload.external_alert_id),
        )
        alert_row = cur.fetchone()
        duplicate = False
        incident_id: Optional[str] = None
        incident_number: Optional[str] = None

        if alert_row:
            duplicate = True
            cur.execute(
                """
                SELECT id::text AS id, incident_number
                FROM incidents
                WHERE tenant_id = %s
                  AND primary_alert_id = %s::uuid
                ORDER BY opened_at DESC
                LIMIT 1;
                """,
                (tenant_id, alert_row["id"]),
            )
            inc = cur.fetchone()
            if inc:
                incident_id = inc["id"]
                incident_number = inc["incident_number"]
            elif _should_create_incident(payload):
                incident_id, incident_number = _create_incident(
                    cur,
                    tenant_id=tenant_id,
                    short_code=short_code,
                    alert_id=alert_row["id"],
                    payload=payload,
                )
                alert_row = {
                    "id": alert_row["id"],
                    "customer_visible": bool(alert_row["customer_visible"]),
                    "status": "incident_created",
                }
        else:
            event_time = payload.event_time or datetime.utcnow()
            cur.execute(
                """
                INSERT INTO security_alerts (
                    tenant_id, source_tool, external_alert_id,
                    severity, alert_title, alert_description, event_time,
                    destination_host, customer_visible, status,
                    ai_plain_summary
                )
                VALUES (
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, false, 'new',
                    %s
                )
                RETURNING id::text AS id, customer_visible, status;
                """,
                (
                    tenant_id,
                    payload.source_tool,
                    payload.external_alert_id,
                    payload.severity,
                    payload.alert_title,
                    payload.alert_description,
                    event_time,
                    payload.destination_host,
                    payload.customer_visible_summary,
                ),
            )
            alert_row = cur.fetchone()

            if _should_create_incident(payload):
                incident_id, incident_number = _create_incident(
                    cur,
                    tenant_id=tenant_id,
                    short_code=short_code,
                    alert_id=alert_row["id"],
                    payload=payload,
                )
                alert_row = {
                    "id": alert_row["id"],
                    "customer_visible": False,
                    "status": "incident_created",
                }

        return (
            {
                "alert_id": alert_row["id"],
                "incident_id": incident_id,
                "incident_number": incident_number,
                "customer_visible": bool(alert_row["customer_visible"]),
                "status": alert_row["status"],
            },
            duplicate,
        )
