"""KB-067: Build and persist customer-safe monthly report snapshots."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from psycopg.types.json import Jsonb

from app.db.session import fetch_all, fetch_one, fetch_one_write
from app.schemas.report_snapshot import empty_snapshot, merge_narrative, project_customer_safe


def _month_bounds(report_month: date) -> tuple[date, date]:
    """Inclusive start (first of month), exclusive end (first of next month)."""
    start = date(report_month.year, report_month.month, 1)
    if report_month.month == 12:
        end = date(report_month.year + 1, 1, 1)
    else:
        end = date(report_month.year, report_month.month + 1, 1)
    return start, end


def _parse_report_month(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)[:10]
    return date.fromisoformat(text)


def build_snapshot(tenant_id: str, report_month: date) -> Dict[str, Any]:
    start, end = _month_bounds(report_month)
    tenant = fetch_one(
        """
        SELECT id::text, name, short_code, sla_level, business_criticality, timezone
        FROM tenants WHERE id = %s;
        """,
        (tenant_id,),
    )
    if not tenant:
        raise ValueError("tenant not found")

    posture_apps = fetch_one(
        """
        SELECT
            count(*) AS appliances_total,
            count(*) FILTER (WHERE status = 'online') AS appliances_online,
            count(*) FILTER (WHERE status = 'offline') AS appliances_offline
        FROM appliances WHERE tenant_id = %s;
        """,
        (tenant_id,),
    )
    assets_total = fetch_one(
        "SELECT count(*) AS n FROM protected_assets WHERE tenant_id = %s;",
        (tenant_id,),
    )
    assets_by_crit = fetch_all(
        """
        SELECT criticality, count(*) AS n
        FROM protected_assets WHERE tenant_id = %s
        GROUP BY criticality;
        """,
        (tenant_id,),
    )

    detection = fetch_one(
        """
        SELECT
            count(*) AS alerts_total,
            count(*) FILTER (WHERE severity = 'critical') AS critical,
            count(*) FILTER (WHERE severity = 'high') AS high,
            count(*) FILTER (WHERE severity = 'medium') AS medium,
            count(*) FILTER (WHERE severity = 'low') AS low,
            count(*) FILTER (WHERE status = 'new') AS status_new,
            count(*) FILTER (WHERE status = 'triaged') AS status_triaged,
            count(*) FILTER (WHERE status = 'incident_created') AS status_incident_created,
            count(*) FILTER (WHERE status = 'false_positive') AS status_false_positive,
            count(*) FILTER (WHERE status = 'closed') AS status_closed
        FROM security_alerts
        WHERE tenant_id = %s
          AND created_at >= %s::timestamptz
          AND created_at < %s::timestamptz;
        """,
        (tenant_id, start.isoformat(), end.isoformat()),
    )

    incidents_summary = fetch_one(
        """
        SELECT
            count(*) FILTER (
                WHERE opened_at >= %s::timestamptz AND opened_at < %s::timestamptz
            ) AS opened,
            count(*) FILTER (
                WHERE closed_at IS NOT NULL
                  AND closed_at >= %s::timestamptz AND closed_at < %s::timestamptz
            ) AS closed,
            count(*) FILTER (
                WHERE status IN ('open', 'in_progress', 'waiting_customer')
            ) AS still_open,
            count(*) FILTER (
                WHERE opened_at >= %s::timestamptz AND opened_at < %s::timestamptz
                  AND severity = 'critical'
            ) AS opened_critical,
            count(*) FILTER (
                WHERE opened_at >= %s::timestamptz AND opened_at < %s::timestamptz
                  AND severity = 'high'
            ) AS opened_high,
            count(*) FILTER (
                WHERE opened_at >= %s::timestamptz AND opened_at < %s::timestamptz
                  AND severity = 'medium'
            ) AS opened_medium,
            count(*) FILTER (
                WHERE opened_at >= %s::timestamptz AND opened_at < %s::timestamptz
                  AND severity = 'low'
            ) AS opened_low
        FROM incidents
        WHERE tenant_id = %s;
        """,
        (
            start.isoformat(),
            end.isoformat(),
            start.isoformat(),
            end.isoformat(),
            start.isoformat(),
            end.isoformat(),
            start.isoformat(),
            end.isoformat(),
            start.isoformat(),
            end.isoformat(),
            start.isoformat(),
            end.isoformat(),
            tenant_id,
        ),
    )

    notable = fetch_all(
        """
        SELECT
            incident_number,
            title,
            severity,
            status,
            customer_visible_summary
        FROM incidents
        WHERE tenant_id = %s
          AND customer_visible_summary IS NOT NULL
          AND btrim(customer_visible_summary) <> ''
          AND (
                (opened_at >= %s::timestamptz AND opened_at < %s::timestamptz)
             OR (closed_at IS NOT NULL AND closed_at >= %s::timestamptz AND closed_at < %s::timestamptz)
          )
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                WHEN 'medium' THEN 3 ELSE 4
            END,
            opened_at DESC NULLS LAST
        LIMIT 25;
        """,
        (
            tenant_id,
            start.isoformat(),
            end.isoformat(),
            start.isoformat(),
            end.isoformat(),
        ),
    )

    rec_counts = fetch_one(
        """
        SELECT
            count(*) FILTER (WHERE status = 'open') AS open_count,
            count(*) FILTER (WHERE status = 'completed') AS completed_count,
            count(*) AS visible_total
        FROM customer_recommendations
        WHERE tenant_id = %s
          AND customer_visible = true
          AND created_at >= %s::timestamptz
          AND created_at < %s::timestamptz;
        """,
        (tenant_id, start.isoformat(), end.isoformat()),
    )
    # Also include currently open visible recommendations regardless of create month
    # so action items stay visible to the customer in the report.
    rec_items = fetch_all(
        """
        SELECT title, priority, status, category, due_at::text
        FROM customer_recommendations
        WHERE tenant_id = %s
          AND customer_visible = true
          AND (
                (created_at >= %s::timestamptz AND created_at < %s::timestamptz)
             OR status IN ('open', 'in_progress')
          )
        ORDER BY
            CASE status WHEN 'open' THEN 1 WHEN 'in_progress' THEN 2 ELSE 3 END,
            CASE priority
                WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                WHEN 'medium' THEN 3 ELSE 4
            END,
            created_at DESC
        LIMIT 50;
        """,
        (tenant_id, start.isoformat(), end.isoformat()),
    )

    notif = fetch_one(
        """
        SELECT
            count(*) FILTER (WHERE status IN ('sent', 'delivered')) AS sent_count,
            count(*) FILTER (WHERE status = 'delivered') AS delivered_count
        FROM notification_events
        WHERE tenant_id = %s
          AND created_at >= %s::timestamptz
          AND created_at < %s::timestamptz;
        """,
        (tenant_id, start.isoformat(), end.isoformat()),
    )
    notif_by_type = fetch_all(
        """
        SELECT notification_type, count(*) AS n
        FROM notification_events
        WHERE tenant_id = %s
          AND created_at >= %s::timestamptz
          AND created_at < %s::timestamptz
        GROUP BY notification_type
        ORDER BY n DESC;
        """,
        (tenant_id, start.isoformat(), end.isoformat()),
    )

    last_day = monthrange(start.year, start.month)[1]
    snap = empty_snapshot()
    snap["generated_at"] = datetime.now(timezone.utc).isoformat()
    snap["period"] = {
        "report_month": start.isoformat(),
        "label": start.strftime("%B %Y"),
        "start": start.isoformat(),
        "end_inclusive": date(start.year, start.month, last_day).isoformat(),
        "end_exclusive": end.isoformat(),
    }
    snap["cover"] = {
        "customer_name": tenant["name"],
        "short_code": tenant["short_code"],
        "sla_level": tenant["sla_level"],
        "business_criticality": tenant["business_criticality"],
        "timezone": tenant.get("timezone") or "Asia/Kolkata",
    }
    snap["posture"] = {
        "appliances_total": int(posture_apps.get("appliances_total") or 0),
        "appliances_online": int(posture_apps.get("appliances_online") or 0),
        "appliances_offline": int(posture_apps.get("appliances_offline") or 0),
        "assets_total": int(assets_total.get("n") or 0),
        "assets_by_criticality": {
            row["criticality"]: int(row["n"]) for row in assets_by_crit
        },
    }
    snap["detection"] = {
        "alerts_total": int(detection.get("alerts_total") or 0),
        "by_severity": {
            "critical": int(detection.get("critical") or 0),
            "high": int(detection.get("high") or 0),
            "medium": int(detection.get("medium") or 0),
            "low": int(detection.get("low") or 0),
        },
        "by_status": {
            "new": int(detection.get("status_new") or 0),
            "triaged": int(detection.get("status_triaged") or 0),
            "incident_created": int(detection.get("status_incident_created") or 0),
            "false_positive": int(detection.get("status_false_positive") or 0),
            "closed": int(detection.get("status_closed") or 0),
        },
    }
    snap["incidents"] = {
        "opened": int(incidents_summary.get("opened") or 0),
        "closed": int(incidents_summary.get("closed") or 0),
        "still_open": int(incidents_summary.get("still_open") or 0),
        "by_severity_opened": {
            "critical": int(incidents_summary.get("opened_critical") or 0),
            "high": int(incidents_summary.get("opened_high") or 0),
            "medium": int(incidents_summary.get("opened_medium") or 0),
            "low": int(incidents_summary.get("opened_low") or 0),
        },
        "notable": [
            {
                "incident_number": row["incident_number"],
                "title": row["title"],
                "severity": row["severity"],
                "status": row["status"],
                "customer_visible_summary": row["customer_visible_summary"],
            }
            for row in notable
        ],
    }
    snap["recommendations"] = {
        "open_count": int(rec_counts.get("open_count") or 0),
        "completed_count": int(rec_counts.get("completed_count") or 0),
        "visible_created_in_month": int(rec_counts.get("visible_total") or 0),
        "items": [
            {
                "title": row["title"],
                "priority": row["priority"],
                "status": row["status"],
                "category": row["category"],
                "due_at": row.get("due_at"),
            }
            for row in rec_items
        ],
    }
    snap["notifications"] = {
        "sent_count": int(notif.get("sent_count") or 0),
        "delivered_count": int(notif.get("delivered_count") or 0),
        "by_type": {row["notification_type"]: int(row["n"]) for row in notif_by_type},
    }
    return snap


def load_stored_metrics(report_id: UUID) -> Dict[str, Any]:
    row = fetch_one(
        "SELECT metrics FROM monthly_reports WHERE id = %s;",
        (str(report_id),),
    )
    metrics = row.get("metrics") if row else None
    return metrics if isinstance(metrics, dict) else {}


def refresh_and_store(
    report_id: UUID,
    narrative_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Rebuild auto sections, preserve narrative, write metrics, return safe projection."""
    row = fetch_one(
        """
        SELECT id::text, tenant_id::text, report_month, metrics
        FROM monthly_reports WHERE id = %s;
        """,
        (str(report_id),),
    )
    if not row:
        raise LookupError("report not found")

    existing = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    snap = build_snapshot(row["tenant_id"], _parse_report_month(row["report_month"]))
    snap = merge_narrative(snap, existing.get("narrative") if isinstance(existing, dict) else None)
    if narrative_override:
        snap = merge_narrative(snap, narrative_override)

    fetch_one_write(
        "UPDATE monthly_reports SET metrics = %s WHERE id = %s RETURNING id::text;",
        (Jsonb(snap), str(report_id)),
    )
    return project_customer_safe(snap)


def ensure_snapshot_for_publish(report_id: UUID) -> Dict[str, Any]:
    """Refresh snapshot when publishing so the issued report is frozen with current numbers."""
    return refresh_and_store(report_id)


def get_safe_sections_for_report(report_id: UUID) -> Dict[str, Any]:
    metrics = load_stored_metrics(report_id)
    if metrics.get("schema_version"):
        return project_customer_safe(metrics)
    # Lazy build for older rows without regenerating into DB unless caller asks.
    row = fetch_one(
        "SELECT tenant_id::text, report_month FROM monthly_reports WHERE id = %s;",
        (str(report_id),),
    )
    if not row:
        return project_customer_safe({})
    snap = build_snapshot(row["tenant_id"], _parse_report_month(row["report_month"]))
    return project_customer_safe(snap)
