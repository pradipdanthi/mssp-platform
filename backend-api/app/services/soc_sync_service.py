"""KB-061: persist normalized SOC alerts/incidents for dashboard visibility."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from psycopg.types.json import Json

from app.db.session import db_transaction
from app.schemas.soc_sync import SocSyncRequest
from app.services.alert_suppressions import try_suppress_alert
from app.services.soc_alert_merge import (
    OPEN_MERGE_STATUSES,
    TERMINAL_STATUSES,
    audit_details,
    higher_severity,
    merge_fingerprint,
    occurrence_summary,
)

logger = logging.getLogger(__name__)

# Correlate same-title bursts into one open incident (minutes).
CORRELATE_WINDOW_MINUTES = int(
    (os.getenv("SOC_INCIDENT_CORRELATE_MINUTES") or "15").strip() or "15"
)


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


def _find_correlated_open_incident(
    cur: Any,
    *,
    tenant_id: str,
    alert_title: str,
    destination_host: Optional[str],
    window_minutes: int,
) -> Optional[Dict[str, str]]:
    """
    Phase-1 burst correlation: reuse an open incident with the same title
    opened within the correlation window. Prefer matching host via primary alert.
    """
    if window_minutes <= 0:
        return None
    host = (destination_host or "").strip()
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
              AND (
                    lower(COALESCE(sa.destination_host, '')) = lower(%s)
                 OR sa.destination_host IS NULL
                 OR btrim(COALESCE(sa.destination_host, '')) = ''
              )
            ORDER BY i.opened_at DESC
            LIMIT 1;
            """,
            (tenant_id, alert_title, window_minutes, host),
        )
    else:
        cur.execute(
            """
            SELECT id::text AS id, incident_number
            FROM incidents
            WHERE tenant_id = %s
              AND title = %s
              AND status IN ('open', 'in_progress', 'waiting_customer')
              AND opened_at >= (now() - make_interval(mins => %s))
            ORDER BY opened_at DESC
            LIMIT 1;
            """,
            (tenant_id, alert_title, window_minutes),
        )
    row = cur.fetchone()
    if not row:
        return None
    return {"id": row["id"], "incident_number": row["incident_number"]}


def _attach_alert_to_incident(
    cur: Any,
    *,
    incident_id: str,
    alert_id: str,
    payload: SocSyncRequest,
) -> None:
    cur.execute(
        """
        INSERT INTO incident_alerts (incident_id, alert_id)
        VALUES (%s::uuid, %s::uuid)
        ON CONFLICT DO NOTHING;
        """,
        (incident_id, alert_id),
    )
    cur.execute(
        """
        INSERT INTO incident_timeline (
            incident_id, event_type, visibility, title, details
        )
        VALUES (
            %s::uuid, 'comment', 'internal',
            'Correlated alert attached',
            %s
        );
        """,
        (
            incident_id,
            (
                f"Burst correlation: attached alert {payload.external_alert_id} "
                f"({payload.source_tool}) host={payload.destination_host or 'n/a'}"
            )[:4000],
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


def _create_or_correlate_incident(
    cur: Any,
    *,
    tenant_id: str,
    short_code: str,
    alert_id: str,
    payload: SocSyncRequest,
) -> Tuple[str, str]:
    # Serialize burst create/correlate so parallel Shuffle webhooks cannot
    # each open a duplicate incident for the same title+host window.
    correlate_key = (
        f"soc-correlate:{tenant_id}:{payload.alert_title}:"
        f"{(payload.destination_host or '').strip().lower()}"
    )
    cur.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0));",
        (correlate_key,),
    )
    existing = _find_correlated_open_incident(
        cur,
        tenant_id=tenant_id,
        alert_title=payload.alert_title,
        destination_host=payload.destination_host,
        window_minutes=CORRELATE_WINDOW_MINUTES,
    )
    if existing:
        logger.info(
            "SOC sync correlated alert to existing incident %s (title=%s host=%s)",
            existing["incident_number"],
            payload.alert_title[:80],
            payload.destination_host,
        )
        _attach_alert_to_incident(
            cur,
            incident_id=existing["id"],
            alert_id=alert_id,
            payload=payload,
        )
        return existing["id"], existing["incident_number"]
    return _create_incident(
        cur,
        tenant_id=tenant_id,
        short_code=short_code,
        alert_id=alert_id,
        payload=payload,
    )


def _resolve_protected_asset_id(
    cur: Any,
    *,
    tenant_id: str,
    wazuh_agent_id: Optional[str],
    destination_host: Optional[str],
) -> Optional[str]:
    """Link alert to protected_assets via Wazuh agent id, then hostname."""
    agent_id = (wazuh_agent_id or "").strip()
    if agent_id:
        cur.execute(
            """
            SELECT id::text AS id
            FROM protected_assets
            WHERE tenant_id = %s::uuid
              AND details->>'wazuh_agent_id' = %s
            ORDER BY updated_at DESC NULLS LAST, created_at DESC
            LIMIT 1;
            """,
            (tenant_id, agent_id),
        )
        row = cur.fetchone()
        if row:
            return row["id"]
    host = (destination_host or "").strip()
    if host:
        cur.execute(
            """
            SELECT id::text AS id
            FROM protected_assets
            WHERE tenant_id = %s::uuid
              AND lower(hostname) = lower(%s)
            ORDER BY updated_at DESC NULLS LAST, created_at DESC
            LIMIT 1;
            """,
            (tenant_id, host),
        )
        row = cur.fetchone()
        if row:
            return row["id"]
    return None


def _safe_inet(value: Optional[str]) -> Optional[str]:
    """Return a value suitable for PostgreSQL inet, or None."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Drop CIDR if present for host-only display consistency.
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    return text or None


def _record_occurrence(
    cur: Any,
    *,
    tenant_id: str,
    alert_id: str,
    payload: SocSyncRequest,
    occurrence_no: int,
    fingerprint: Optional[str],
    audit_action: str,
    sla_first_seen_preserved: bool,
) -> None:
    cur.execute(
        """
        INSERT INTO security_alert_occurrences (
            tenant_id, alert_id, source_tool, external_alert_id,
            occurrence_no, event_time, severity, fingerprint, summary
        )
        VALUES (
            %s, %s::uuid, %s, %s,
            %s, %s, %s, %s, %s
        )
        ON CONFLICT (tenant_id, source_tool, external_alert_id) DO NOTHING;
        """,
        (
            tenant_id,
            alert_id,
            payload.source_tool,
            payload.external_alert_id,
            occurrence_no,
            payload.event_time or datetime.utcnow(),
            payload.severity,
            fingerprint,
            occurrence_summary(payload),
        ),
    )
    details = audit_details(
        parent_id=alert_id,
        occurrence_no=occurrence_no,
        payload=payload,
        fingerprint=fingerprint or "",
        sla_first_seen_preserved=sla_first_seen_preserved,
    )
    cur.execute(
        """
        INSERT INTO audit_logs (
            tenant_id, action, entity_type, entity_id, details,
            actor_role, action_status, resource_type, resource_id
        )
        VALUES (
            %s, %s, 'security_alert', %s::uuid, %s,
            'system', 'SUCCESS', 'security_alert', %s
        );
        """,
        (tenant_id, audit_action, alert_id, Json(details), alert_id),
    )


def _find_open_parent(cur: Any, *, tenant_id: str, fingerprint: str) -> Optional[Dict[str, Any]]:
    cur.execute(
        """
        SELECT id::text AS id, customer_visible, status,
               occurrence_count, first_seen_at, created_at, severity
        FROM security_alerts
        WHERE tenant_id = %s
          AND merge_fingerprint = %s
          AND status = ANY(%s)
        ORDER BY created_at ASC
        LIMIT 1
        FOR UPDATE;
        """,
        (tenant_id, fingerprint, list(OPEN_MERGE_STATUSES)),
    )
    return cur.fetchone()


def _find_closed_parent(cur: Any, *, tenant_id: str, fingerprint: str) -> Optional[str]:
    cur.execute(
        """
        SELECT id::text AS id
        FROM security_alerts
        WHERE tenant_id = %s
          AND merge_fingerprint = %s
          AND status = ANY(%s)
        ORDER BY created_at DESC
        LIMIT 1;
        """,
        (tenant_id, fingerprint, list(TERMINAL_STATUSES)),
    )
    row = cur.fetchone()
    return str(row["id"]) if row else None


def _merge_into_parent(
    cur: Any,
    *,
    tenant_id: str,
    parent: Dict[str, Any],
    payload: SocSyncRequest,
    fingerprint: str,
) -> Dict[str, Any]:
    """Attach this engine event to the open parent. Does not reset SLA clocks."""
    next_no = int(parent.get("occurrence_count") or 1) + 1
    new_sev = higher_severity(parent.get("severity"), payload.severity)
    cur.execute(
        """
        UPDATE security_alerts
        SET occurrence_count = %s,
            last_seen_at = GREATEST(COALESCE(last_seen_at, created_at), %s::timestamptz, now()),
            severity = %s,
            updated_at = now()
        WHERE id = %s::uuid
          AND status = ANY(%s)
        RETURNING id::text AS id, customer_visible, status,
                  occurrence_count, first_seen_at, created_at, severity;
        """,
        (
            next_no,
            payload.event_time or datetime.utcnow(),
            new_sev,
            parent["id"],
            list(OPEN_MERGE_STATUSES),
        ),
    )
    updated = cur.fetchone() or parent
    _record_occurrence(
        cur,
        tenant_id=tenant_id,
        alert_id=str(updated["id"]),
        payload=payload,
        occurrence_no=int(updated.get("occurrence_count") or next_no),
        fingerprint=fingerprint,
        audit_action="alert_occurrence_merged",
        sla_first_seen_preserved=True,
    )
    cur.execute(
        """
        SELECT id::text AS id, incident_number
        FROM incidents
        WHERE tenant_id = %s
          AND primary_alert_id = %s::uuid
        ORDER BY opened_at DESC
        LIMIT 1;
        """,
        (tenant_id, updated["id"]),
    )
    inc = cur.fetchone()
    if inc:
        cur.execute(
            """
            INSERT INTO incident_timeline (
                incident_id, event_type, visibility, title, details
            )
            VALUES (
                %s::uuid, 'comment', 'internal',
                'Identical detection merged',
                %s
            );
            """,
            (
                inc["id"],
                (
                    f"Occurrence {updated.get('occurrence_count')} of the same detection "
                    f"on {payload.destination_host or 'n/a'} "
                    f"(engine id {payload.external_alert_id}). "
                    f"SLA first-seen was not reset."
                )[:4000],
            ),
        )
    logger.info(
        "SOC sync merged occurrence %s into alert %s fingerprint=%s",
        updated.get("occurrence_count"),
        updated["id"],
        fingerprint[:80],
    )
    return {
        "id": updated["id"],
        "customer_visible": bool(updated.get("customer_visible")),
        "status": updated.get("status") or parent.get("status"),
        "occurrence_count": int(updated.get("occurrence_count") or next_no),
        "incident_id": inc["id"] if inc else None,
        "incident_number": inc["incident_number"] if inc else None,
    }


def sync_soc_alert(payload: SocSyncRequest) -> Tuple[Dict[str, Any], bool]:
    """
    Insert or return existing security_alerts row; optionally create incident.

    Dedup keys, in order:
      1. exact engine id (tenant + source_tool + external_alert_id)
      2. open occurrence merge (same tenant/rule/host/behaviour)
    Closed parents never absorb a later hit. first_seen_at is immutable.
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

        asset_id = _resolve_protected_asset_id(
            cur,
            tenant_id=tenant_id,
            wazuh_agent_id=getattr(payload, "wazuh_agent_id", None),
            destination_host=payload.destination_host,
        )
        source_ip = _safe_inet(getattr(payload, "source_ip", None))
        destination_ip = _safe_inet(
            getattr(payload, "destination_ip", None) or source_ip
        )
        source_user = (getattr(payload, "source_user", None) or None)
        technical_summary = (getattr(payload, "technical_summary", None) or None)

        cur.execute(
            """
            SELECT o.alert_id::text AS id, sa.customer_visible, sa.status,
                   sa.occurrence_count
            FROM security_alert_occurrences o
            JOIN security_alerts sa ON sa.id = o.alert_id
            WHERE o.tenant_id = %s
              AND o.source_tool = %s
              AND o.external_alert_id = %s
            LIMIT 1;
            """,
            (tenant_id, payload.source_tool, payload.external_alert_id),
        )
        existing_occ = cur.fetchone()
        cur.execute(
            """
            SELECT id::text AS id, customer_visible, status, occurrence_count
            FROM security_alerts
            WHERE tenant_id = %s
              AND source_tool = %s
              AND external_alert_id = %s
            ORDER BY created_at
            LIMIT 1;
            """,
            (tenant_id, payload.source_tool, payload.external_alert_id),
        )
        alert_row = existing_occ or cur.fetchone()
        duplicate = False
        merged = False
        incident_id: Optional[str] = None
        incident_number: Optional[str] = None
        fingerprint = merge_fingerprint(payload)

        if alert_row:
            duplicate = True
            # Backfill enrichment columns that may have been empty on older rows.
            cur.execute(
                """
                UPDATE security_alerts
                SET asset_id = COALESCE(asset_id, %s::uuid),
                    source_ip = COALESCE(source_ip, %s::inet),
                    destination_ip = COALESCE(destination_ip, %s::inet),
                    source_user = COALESCE(NULLIF(source_user, ''), %s),
                    destination_host = COALESCE(NULLIF(destination_host, ''), %s),
                    ai_technical_summary = COALESCE(
                        NULLIF(ai_technical_summary, ''), %s
                    ),
                    updated_at = now()
                WHERE id = %s::uuid;
                """,
                (
                    asset_id,
                    source_ip,
                    destination_ip,
                    source_user,
                    payload.destination_host,
                    technical_summary,
                    alert_row["id"],
                ),
            )
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
                suppressed = try_suppress_alert(
                    cur,
                    tenant_id=tenant_id,
                    alert_id=alert_row["id"],
                    destination_host=payload.destination_host,
                    rule_id=payload.rule_id,
                )
                if suppressed:
                    alert_row = {
                        "id": alert_row["id"],
                        "customer_visible": False,
                        "status": "false_positive",
                    }
                else:
                    incident_id, incident_number = _create_or_correlate_incident(
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
            if fingerprint:
                merge_lock = f"soc-merge:{tenant_id}:{fingerprint}"
                cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0));",
                    (merge_lock,),
                )
                parent = _find_open_parent(
                    cur, tenant_id=tenant_id, fingerprint=fingerprint
                )
                if parent:
                    merged_row = _merge_into_parent(
                        cur,
                        tenant_id=tenant_id,
                        parent=parent,
                        payload=payload,
                        fingerprint=fingerprint,
                    )
                    duplicate = True
                    merged = True
                    alert_row = {
                        "id": merged_row["id"],
                        "customer_visible": merged_row["customer_visible"],
                        "status": merged_row["status"],
                        "occurrence_count": merged_row["occurrence_count"],
                    }
                    incident_id = merged_row.get("incident_id")
                    incident_number = merged_row.get("incident_number")

            if not merged:
                event_time = payload.event_time or datetime.utcnow()
                initial_status = (
                    "false_positive" if payload.create_incident is False else "new"
                )
                # Customer-safe normalized rows are visible on the tenant portal.
                # False positives stay hidden. SOC can still hide a row in triage.
                customer_visible = initial_status != "false_positive"
                recurrence_of = (
                    _find_closed_parent(
                        cur, tenant_id=tenant_id, fingerprint=fingerprint
                    )
                    if fingerprint
                    else None
                )
                cur.execute(
                    """
                    INSERT INTO security_alerts (
                        tenant_id, source_tool, external_alert_id,
                        severity, alert_title, alert_description, event_time,
                        destination_host, destination_ip, source_ip, source_user,
                        asset_id, customer_visible, status,
                        ai_plain_summary, ai_technical_summary,
                        occurrence_count, first_seen_at, last_seen_at,
                        merge_fingerprint, recurrence_of_alert_id
                    )
                    VALUES (
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s::inet, %s::inet, %s,
                        %s::uuid, %s, %s,
                        %s, %s,
                        1, %s, %s,
                        %s, %s::uuid
                    )
                    RETURNING id::text AS id, customer_visible, status, occurrence_count;
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
                        destination_ip,
                        source_ip,
                        source_user,
                        asset_id,
                        customer_visible,
                        initial_status,
                        payload.customer_visible_summary,
                        technical_summary,
                        event_time,
                        event_time,
                        fingerprint,
                        recurrence_of,
                    ),
                )
                alert_row = cur.fetchone()
                _record_occurrence(
                    cur,
                    tenant_id=tenant_id,
                    alert_id=alert_row["id"],
                    payload=payload,
                    occurrence_no=1,
                    fingerprint=fingerprint,
                    audit_action=(
                        "alert_recurrence_opened"
                        if recurrence_of
                        else "alert_occurrence_recorded"
                    ),
                    sla_first_seen_preserved=False,
                )

                suppressed = try_suppress_alert(
                    cur,
                    tenant_id=tenant_id,
                    alert_id=alert_row["id"],
                    destination_host=payload.destination_host,
                    rule_id=payload.rule_id,
                )
                if suppressed:
                    alert_row = {
                        "id": alert_row["id"],
                        "customer_visible": False,
                        "status": "false_positive",
                    }
                elif _should_create_incident(payload):
                    incident_id, incident_number = _create_or_correlate_incident(
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

        result = {
            "alert_id": alert_row["id"],
            "incident_id": incident_id,
            "incident_number": incident_number,
            "customer_visible": bool(alert_row["customer_visible"]),
            "status": alert_row["status"],
            "merged": merged,
            "occurrence_count": int(alert_row.get("occurrence_count") or 1),
        }

    # Enqueue only after the alert row is committed. tia_jobs.alert_id is a
    # foreign key; a second connection cannot see the insert until COMMIT.
    # Merged occurrences must not start a second investigation or a new SLA job.
    if not duplicate:
        try:
            from app.services.ai_alert_queue import enqueue_ai_alert_analysis

            enqueue_ai_alert_analysis(
                alert_id=str(result["alert_id"]),
                tenant_id=str(tenant_id),
                severity=payload.severity,
            )
        except Exception:  # noqa: BLE001
            logger.exception("AI alert enqueue failed for alert_id=%s", result["alert_id"])

    return result, duplicate
