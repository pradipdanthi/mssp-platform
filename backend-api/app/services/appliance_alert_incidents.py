"""Create/correlate SOC incidents for appliance-forwarded high/critical alerts."""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

CORRELATE_WINDOW_MINUTES = int(
    (os.getenv("APPLIANCE_INCIDENT_CORRELATE_MINUTES") or "15").strip() or "15"
)


def _next_incident_number(cur: Any, short_code: str) -> str:
    prefix = f"INC-{short_code}-APP-"
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
    suffix = str(last).rsplit("-", 1)[-1]
    try:
        n = int(suffix) + 1
    except ValueError:
        n = int(secrets.randbelow(9000) + 1000)
    return f"{prefix}{n:04d}"


def ensure_incident_for_appliance_alert(
    cur: Any,
    *,
    tenant_id: str,
    short_code: str,
    alert_id: str,
    severity: str,
    alert_title: str,
    destination_host: Optional[str],
) -> Optional[Tuple[str, str]]:
    """
    For high/critical appliance-forwarded alerts, open or correlate an incident.
    Returns (incident_id, incident_number) or None when severity is below threshold.
    """
    sev = (severity or "").lower()
    if sev not in ("high", "critical"):
        return None

    window = max(0, CORRELATE_WINDOW_MINUTES)
    host = (destination_host or "").strip()
    existing = None
    if window > 0:
        if host:
            cur.execute(
                """
                SELECT i.id::text AS id, i.incident_number
                FROM incidents i
                LEFT JOIN security_alerts sa ON sa.id = i.primary_alert_id
                WHERE i.tenant_id = %s
                  AND i.title = %s
                  AND i.status IN ('open', 'in_progress', 'waiting_customer')
                  AND i.opened_at >= (now() - make_interval(mins => %s))
                  AND COALESCE(sa.destination_host, '') = %s
                ORDER BY i.opened_at DESC
                LIMIT 1;
                """,
                (tenant_id, alert_title, window, host),
            )
        else:
            cur.execute(
                """
                SELECT i.id::text AS id, i.incident_number
                FROM incidents i
                WHERE i.tenant_id = %s
                  AND i.title = %s
                  AND i.status IN ('open', 'in_progress', 'waiting_customer')
                  AND i.opened_at >= (now() - make_interval(mins => %s))
                ORDER BY i.opened_at DESC
                LIMIT 1;
                """,
                (tenant_id, alert_title, window),
            )
        existing = cur.fetchone()

    if existing:
        return existing["id"], existing["incident_number"]

    number = _next_incident_number(cur, short_code)
    cur.execute(
        """
        INSERT INTO incidents (
            tenant_id, primary_alert_id, incident_number, title, severity,
            status, opened_at
        )
        VALUES (
            %s::uuid, %s::uuid, %s, %s, %s,
            'open', now()
        )
        RETURNING id::text, incident_number;
        """,
        (tenant_id, alert_id, number, alert_title[:500], sev),
    )
    row = cur.fetchone()
    cur.execute(
        """
        INSERT INTO incident_alerts (incident_id, alert_id)
        VALUES (%s::uuid, %s::uuid)
        ON CONFLICT DO NOTHING;
        """,
        (row["id"], alert_id),
    )
    cur.execute(
        """
        UPDATE security_alerts
        SET status = 'incident_created', updated_at = now()
        WHERE id = %s::uuid;
        """,
        (alert_id,),
    )
    logger.info(
        "appliance alert incident created tenant=%s incident=%s alert=%s",
        short_code,
        row["incident_number"],
        alert_id,
    )
    return row["id"], row["incident_number"]
