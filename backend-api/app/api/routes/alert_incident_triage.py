"""KB-056 Admin/SOC alert and incident detail and triage endpoints."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import require_roles
from app.db.session import fetch_all, fetch_one, fetch_one_write
from app.services.audit_service import audit_from_user
from app.services.ai_tier1_triage import run_tier1_triage
from app.services.soc_alert_taxonomy import enrich_alert_row
from app.schemas.triage import (
    AlertTriageUpdateRequest,
    IncidentCommentCreateRequest,
    IncidentTriageUpdateRequest,
)
from app.schemas.suppressions import BulkAlertsRequest, BulkIncidentsRequest

router = APIRouter(prefix="/admin", tags=["admin-triage"])

ADMIN_SOC_ROLES = ("platform_admin", "soc_manager", "soc_analyst")
ALERT_TRIAGE_WRITE_ROLES = ("platform_admin", "soc_manager")
# Bulk FP/close allowed for analysts per SOC suppressions plan.
BULK_TRIAGE_ROLES = ("platform_admin", "soc_manager", "soc_analyst")


def _alert_detail(alert_id: UUID) -> Dict[str, Any]:
    alert = fetch_one(
        """
        SELECT
            sa.id::text,
            sa.tenant_id::text,
            t.name AS tenant_name,
            t.short_code,
            sa.appliance_id::text,
            a.appliance_name,
            sa.asset_id::text,
            pa.hostname AS asset_hostname,
            pa.asset_type AS asset_type,
            pa.os_name AS asset_os_name,
            CASE WHEN pa.ip_address IS NOT NULL THEN host(pa.ip_address)::text ELSE NULL END AS asset_ip,
            pa.criticality AS asset_criticality,
            pa.owner AS asset_owner,
            pa.details AS asset_details,
            t.timezone AS tenant_timezone,
            sa.source_tool,
            sa.external_alert_id,
            sa.severity,
            sa.alert_title,
            sa.alert_description,
            sa.event_time,
            CASE WHEN sa.source_ip IS NOT NULL THEN host(sa.source_ip)::text ELSE NULL END AS source_ip,
            CASE WHEN sa.destination_ip IS NOT NULL THEN host(sa.destination_ip)::text ELSE NULL END AS destination_ip,
            sa.source_user,
            sa.destination_host,
            sa.raw_event,
            sa.win_eventdata,
            sa.wazuh_full_log,
            sa.parent_process,
            sa.parent_command_line,
            sa.current_directory,
            sa.integrity_level,
            sa.process_guid,
            sa.parent_process_guid,
            sa.logon_id,
            sa.logon_guid,
            sa.hashes_raw,
            sa.hash_md5,
            sa.hash_sha256,
            sa.hash_imphash,
            sa.process_id,
            sa.parent_process_id,
            sa.user_sid,
            sa.ai_plain_summary,
            sa.ai_technical_summary,
            sa.ai_likely_attack_type,
            sa.ai_business_impact,
            sa.ai_recommended_action,
            sa.ai_false_positive_score,
            sa.ai_risk_score,
            sa.ai_risk_rationale,
            sa.ai_enrichment_notes,
            sa.ai_correlation_notes,
            sa.ai_containment_suggestion,
            sa.ai_triage_status,
            sa.ai_triaged_at,
            sa.ai_verdict,
            sa.ai_confidence,
            sa.ai_queue,
            sa.ai_auto_closed,
            sa.ai_resolution_label,
            sa.mitre_mapping,
            sa.customer_visible,
            sa.status,
            sa.created_at,
            sa.updated_at
        FROM security_alerts sa
        JOIN tenants t ON t.id = sa.tenant_id
        LEFT JOIN appliances a ON a.id = sa.appliance_id
        LEFT JOIN protected_assets pa ON pa.id = sa.asset_id
        WHERE sa.id = %s;
        """,
        (alert_id,),
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return enrich_alert_row(alert)


def _incident_detail(incident_id: UUID) -> Dict[str, Any]:
    incident = fetch_one(
        """
        SELECT
            i.id::text,
            i.tenant_id::text,
            t.name AS tenant_name,
            t.short_code,
            i.primary_alert_id::text,
            i.incident_number,
            i.title,
            i.severity,
            i.status,
            i.assigned_to_user_id::text,
            assigned.full_name AS assigned_to,
            i.customer_visible_summary,
            i.business_impact,
            i.customer_action_required,
            i.resolution_summary,
            i.internal_notes,
            i.opened_at,
            i.resolved_at,
            i.closed_at,
            i.created_at,
            i.updated_at
        FROM incidents i
        JOIN tenants t ON t.id = i.tenant_id
        LEFT JOIN platform_users assigned ON assigned.id = i.assigned_to_user_id
        WHERE i.id = %s;
        """,
        (incident_id,),
    )
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    primary_alert: Optional[Dict[str, Any]] = None
    if incident.get("primary_alert_id"):
        try:
            primary_alert = _alert_detail(UUID(str(incident["primary_alert_id"])))
        except HTTPException:
            primary_alert = None

    timeline = fetch_all(
        """
        SELECT
            it.id::text,
            it.event_type,
            it.visibility,
            it.title,
            it.details,
            it.created_by_user_id::text,
            creator.full_name AS created_by,
            it.created_at
        FROM incident_timeline it
        LEFT JOIN platform_users creator ON creator.id = it.created_by_user_id
        WHERE it.incident_id = %s
        ORDER BY it.created_at ASC;
        """,
        (incident_id,),
    )
    comments = fetch_all(
        """
        SELECT
            ic.id::text,
            ic.visibility,
            ic.comment_text,
            ic.created_by_user_id::text,
            creator.full_name AS created_by,
            ic.created_at
        FROM incident_comments ic
        LEFT JOIN platform_users creator ON creator.id = ic.created_by_user_id
        WHERE ic.incident_id = %s
        ORDER BY ic.created_at ASC;
        """,
        (incident_id,),
    )
    return {
        "incident": incident,
        "primary_alert": primary_alert,
        "timeline": timeline,
        "comments": comments,
    }


@router.get("/alerts/{alert_id}")
def get_admin_alert_detail(
    alert_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    return {"alert": _alert_detail(alert_id)}


@router.get("/alerts/{alert_id}/ai-triage")
@router.post("/alerts/{alert_id}/ai-triage")
def admin_alert_ai_triage(
    alert_id: UUID,
    force: bool = Query(default=False),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """
    Tier-1 AI SOC triage (on-demand). Proxies to Ollama with 8s timeout;
    returns DB cache instantly on identical payload hash.
    """
    alert = _alert_detail(alert_id)
    try:
        triage = run_tier1_triage(
            alert_id=str(alert_id),
            tenant_id=str(alert["tenant_id"]),
            alert=alert,
            customer_safe=False,
            force=force,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc) or "AI triage timed out",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI triage failed: {exc}",
        ) from exc
    return {"alert_id": str(alert_id), "triage": triage}


@router.patch("/alerts/{alert_id}")
def update_admin_alert_triage(
    alert_id: UUID,
    payload: AlertTriageUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ALERT_TRIAGE_WRITE_ROLES)),
) -> Dict[str, Any]:
    assignments = []
    values = []
    if "status" in payload.model_fields_set:
        assignments.append("status = %s")
        values.append(payload.status)
    hide_from_customer = (
        "status" in payload.model_fields_set and payload.status == "false_positive"
    )
    if hide_from_customer:
        assignments.append("customer_visible = %s")
        values.append(False)
    elif "customer_visible" in payload.model_fields_set:
        assignments.append("customer_visible = %s")
        values.append(payload.customer_visible)
    if "ai_plain_summary" in payload.model_fields_set:
        assignments.append("ai_plain_summary = %s")
        values.append(payload.ai_plain_summary)
    if "ai_recommended_action" in payload.model_fields_set:
        assignments.append("ai_recommended_action = %s")
        values.append(payload.ai_recommended_action)
    if "ai_triage_status" in payload.model_fields_set:
        assignments.append("ai_triage_status = %s")
        values.append(payload.ai_triage_status)
    assignments.append("updated_at = now()")
    values.append(alert_id)

    updated = fetch_one_write(
        f"""
        UPDATE security_alerts
        SET {", ".join(assignments)}
        WHERE id = %s
        RETURNING id::text;
        """,
        tuple(values),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return {"alert": _alert_detail(alert_id)}


@router.get("/incidents/{incident_id}")
def get_admin_incident_detail(
    incident_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    return _incident_detail(incident_id)


@router.patch("/incidents/{incident_id}")
def update_admin_incident_triage(
    incident_id: UUID,
    payload: IncidentTriageUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    if "assigned_to_user_id" in payload.model_fields_set and payload.assigned_to_user_id is not None:
        assignee = fetch_one(
            """
            SELECT id::text
            FROM platform_users
            WHERE id = %s
              AND role IN ('platform_admin', 'soc_manager', 'soc_analyst')
              AND status = 'active';
            """,
            (payload.assigned_to_user_id,),
        )
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Assignee must be an active Admin/SOC user",
            )

    assignments = []
    values = []
    if "status" in payload.model_fields_set:
        assignments.append("status = %s")
        values.append(payload.status)
    if "assigned_to_user_id" in payload.model_fields_set:
        assignments.append("assigned_to_user_id = %s")
        values.append(payload.assigned_to_user_id)
    if "customer_visible_summary" in payload.model_fields_set:
        assignments.append("customer_visible_summary = %s")
        values.append(payload.customer_visible_summary)
    if "customer_action_required" in payload.model_fields_set:
        assignments.append("customer_action_required = %s")
        values.append(payload.customer_action_required)
    assignments.append("updated_at = now()")
    values.append(incident_id)

    updated = fetch_one_write(
        f"""
        UPDATE incidents
        SET {", ".join(assignments)}
        WHERE id = %s
        RETURNING id::text;
        """,
        tuple(values),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return _incident_detail(incident_id)


@router.post("/incidents/{incident_id}/comments", status_code=status.HTTP_201_CREATED)
def create_admin_incident_comment(
    incident_id: UUID,
    payload: IncidentCommentCreateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    if not fetch_one("SELECT id::text FROM incidents WHERE id = %s;", (incident_id,)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    comment = fetch_one_write(
        """
        INSERT INTO incident_comments (
            incident_id,
            created_by_user_id,
            visibility,
            comment_text
        )
        VALUES (%s, %s, %s, %s)
        RETURNING
            id::text,
            visibility,
            comment_text,
            created_by_user_id::text,
            created_at;
        """,
        (incident_id, current_user["id"], payload.visibility, payload.comment_text),
    )
    comment["created_by"] = current_user["full_name"]
    return {"comment": comment}


@router.post("/alerts/bulk")
def bulk_update_admin_alerts(
    payload: BulkAlertsRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*BULK_TRIAGE_ROLES)),
) -> Dict[str, Any]:
    """
    Bulk mark alerts false_positive or closed, or approve AI low-priority
    closures (close as FP + optional suppressions from cached AI scope).
    """
    if payload.action == "approve_ai_low_priority":
        return _bulk_approve_ai_low_priority(payload, current_user)

    updated_ids: List[str] = []
    missing_ids: List[str] = []
    reason_note = (payload.reason or "").strip()
    status_value = payload.status or "closed"

    for alert_id in payload.alert_ids:
        assignments = ["status = %s", "updated_at = now()"]
        values: list = [status_value]
        if status_value == "false_positive":
            assignments.append("customer_visible = false")
        if reason_note:
            assignments.append(
                "ai_technical_summary = CASE "
                "WHEN ai_technical_summary IS NULL OR btrim(ai_technical_summary) = '' "
                "THEN %s "
                "ELSE left(ai_technical_summary || E'\\n' || %s, 4000) END"
            )
            note = f"Bulk triage ({status_value}) by {current_user.get('email')}: {reason_note}"[
                :4000
            ]
            values.extend([note, note])
        values.append(alert_id)
        row = fetch_one_write(
            f"""
            UPDATE security_alerts
            SET {", ".join(assignments)}
            WHERE id = %s
            RETURNING id::text;
            """,
            tuple(values),
        )
        if row:
            updated_ids.append(row["id"])
        else:
            missing_ids.append(str(alert_id))

    audit_from_user(
        current_user,
        action="alerts.bulk_update",
        entity_type="security_alert",
        details={
            "status": status_value,
            "updated_count": len(updated_ids),
            "missing_count": len(missing_ids),
            "alert_ids": updated_ids[:50],
            "reason": reason_note or None,
        },
    )
    return {
        "updated": len(updated_ids),
        "updated_ids": updated_ids,
        "missing_ids": missing_ids,
        "status": status_value,
    }


def _bulk_approve_ai_low_priority(
    payload: BulkAlertsRequest,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Approve Low-Priority / AI Reviewed items: mark false_positive + hide from
    customer, clear ai_queue, and create tenant/host suppressions from the
    latest cached AI suggested_suppression_scope when present and safe.
    """
    import json as _json

    updated_ids: List[str] = []
    missing_ids: List[str] = []
    skipped_ids: List[str] = []
    suppressions_created: List[str] = []
    reason_note = (payload.reason or "").strip() or (
        "Approved AI low-priority closure (human confirm)"
    )
    actor = current_user.get("email") or current_user.get("full_name") or "soc"

    for alert_id in payload.alert_ids:
        row = fetch_one(
            """
            SELECT
              sa.id::text,
              sa.tenant_id::text,
              sa.ai_queue,
              sa.ai_verdict,
              sa.ai_confidence,
              sa.status,
              sa.destination_host,
              pa.hostname AS asset_hostname,
              COALESCE(
                NULLIF(btrim(sa.raw_event #>> '{rule,id}'), ''),
                NULLIF(btrim(sa.raw_event #>> '{data,win,system,providerName}'), '')
              ) AS raw_rule_hint
            FROM security_alerts sa
            LEFT JOIN protected_assets pa ON pa.id = sa.asset_id
            WHERE sa.id = %s::uuid;
            """,
            (alert_id,),
        )
        if not row:
            missing_ids.append(str(alert_id))
            continue
        # Only approve items already routed to low_priority (or matching rule).
        is_lp = (
            row.get("ai_queue") == "low_priority"
            or (
                row.get("ai_verdict") == "BENIGN_FALSE_POSITIVE"
                and row.get("ai_confidence") is not None
                and float(row["ai_confidence"]) >= 85
            )
        )
        if not is_lp:
            skipped_ids.append(str(alert_id))
            continue

        note = f"Approve AI low-priority by {actor}: {reason_note}"[:4000]
        updated = fetch_one_write(
            """
            UPDATE security_alerts
            SET status = 'false_positive',
                customer_visible = false,
                ai_queue = NULL,
                ai_resolution_label = COALESCE(ai_resolution_label, 'Closed (AI Low-Priority Approved)'),
                ai_technical_summary = CASE
                  WHEN ai_technical_summary IS NULL OR btrim(ai_technical_summary) = ''
                  THEN %s
                  ELSE left(ai_technical_summary || E'\\n' || %s, 4000)
                END,
                updated_at = now()
            WHERE id = %s::uuid
            RETURNING id::text;
            """,
            (note, note, alert_id),
        )
        if not updated:
            missing_ids.append(str(alert_id))
            continue
        updated_ids.append(updated["id"])

        if not payload.create_suppressions:
            continue

        cache = fetch_one(
            """
            SELECT suggested_suppression_scope
            FROM alert_ai_triage_cache
            WHERE alert_id = %s::uuid
            ORDER BY updated_at DESC
            LIMIT 1;
            """,
            (alert_id,),
        )
        scope = (cache or {}).get("suggested_suppression_scope") or {}
        if isinstance(scope, str):
            try:
                scope = _json.loads(scope)
            except (TypeError, ValueError):
                scope = {}
        if not isinstance(scope, dict):
            scope = {}
        rule_id = str(scope.get("rule_id") or "").strip()
        process_path = str(scope.get("process_path") or "").strip()
        justification = str(scope.get("justification") or reason_note).strip()[:4000]
        if not rule_id:
            continue

        hostname = (
            str(row.get("asset_hostname") or row.get("destination_host") or "").strip()
            or None
        )
        # Prefer host scope when hostname known; else tenant.
        if hostname:
            supp_scope = "host"
            match_hostname = True
            hostname_value = hostname
        else:
            supp_scope = "tenant"
            match_hostname = False
            hostname_value = None

        match_path = bool(process_path)
        try:
            supp = fetch_one_write(
                """
                INSERT INTO alert_suppressions (
                    tenant_id, hostname, rule_id, scope,
                    match_process_path, process_path_value,
                    match_parent_process, parent_process_value,
                    match_file_hash, file_hash_value,
                    match_hostname, hostname_value,
                    expires_at, reason, created_by_user_id
                )
                VALUES (
                    %s::uuid, %s, %s, %s,
                    %s, %s,
                    false, NULL,
                    false, NULL,
                    %s, %s,
                    NULL, %s, %s::uuid
                )
                RETURNING id::text;
                """,
                (
                    row["tenant_id"],
                    hostname if supp_scope == "host" else None,
                    rule_id[:128],
                    supp_scope,
                    match_path,
                    process_path[:1000] if match_path else None,
                    match_hostname,
                    hostname_value,
                    f"AI low-priority approve: {justification}"[:4000],
                    current_user["id"],
                ),
            )
            if supp:
                suppressions_created.append(supp["id"])
        except Exception:  # noqa: BLE001
            # Soft-fail suppression create; alert was still closed.
            pass

    audit_from_user(
        current_user,
        action="alerts.approve_ai_low_priority",
        entity_type="security_alert",
        details={
            "updated_count": len(updated_ids),
            "missing_count": len(missing_ids),
            "skipped_count": len(skipped_ids),
            "suppressions_created": len(suppressions_created),
            "alert_ids": updated_ids[:50],
            "suppression_ids": suppressions_created[:50],
            "reason": reason_note,
            "create_suppressions": payload.create_suppressions,
        },
    )
    return {
        "updated": len(updated_ids),
        "updated_ids": updated_ids,
        "missing_ids": missing_ids,
        "skipped_ids": skipped_ids,
        "suppressions_created": len(suppressions_created),
        "suppression_ids": suppressions_created,
        "status": "false_positive",
        "action": "approve_ai_low_priority",
    }


@router.post("/incidents/bulk")
def bulk_update_admin_incidents(
    payload: BulkIncidentsRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*BULK_TRIAGE_ROLES)),
) -> Dict[str, Any]:
    """Bulk close/resolve incidents with a required close_reason enum."""
    updated_ids: List[str] = []
    missing_ids: List[str] = []
    reason_label = payload.close_reason.replace("_", " ")
    note = (
        f"Bulk {payload.status} ({reason_label}) by "
        f"{current_user.get('full_name') or current_user.get('email')}"
    )[:4000]

    for incident_id in payload.incident_ids:
        if payload.status == "resolved":
            row = fetch_one_write(
                """
                UPDATE incidents
                SET status = 'resolved',
                    resolved_at = COALESCE(resolved_at, now()),
                    resolution_summary = COALESCE(
                        NULLIF(btrim(resolution_summary), ''),
                        %s
                    ),
                    updated_at = now()
                WHERE id = %s
                RETURNING id::text;
                """,
                (note, incident_id),
            )
        else:
            row = fetch_one_write(
                """
                UPDATE incidents
                SET status = 'closed',
                    closed_at = COALESCE(closed_at, now()),
                    resolution_summary = COALESCE(
                        NULLIF(btrim(resolution_summary), ''),
                        %s
                    ),
                    updated_at = now()
                WHERE id = %s
                RETURNING id::text;
                """,
                (note, incident_id),
            )
        if not row:
            missing_ids.append(str(incident_id))
            continue
        updated_ids.append(row["id"])
        fetch_one_write(
            """
            INSERT INTO incident_timeline (
                incident_id, event_type, visibility, title, details, created_by_user_id
            )
            VALUES (
                %s::uuid, 'status_changed', 'internal',
                %s, %s, %s::uuid
            )
            RETURNING id::text;
            """,
            (
                row["id"],
                f"Bulk status → {payload.status}",
                f"close_reason={payload.close_reason}",
                current_user["id"],
            ),
        )

    audit_from_user(
        current_user,
        action="incidents.bulk_update",
        entity_type="incident",
        details={
            "status": payload.status,
            "close_reason": payload.close_reason,
            "updated_count": len(updated_ids),
            "missing_count": len(missing_ids),
            "incident_ids": updated_ids[:50],
        },
    )
    return {
        "updated": len(updated_ids),
        "updated_ids": updated_ids,
        "missing_ids": missing_ids,
        "status": payload.status,
        "close_reason": payload.close_reason,
    }
