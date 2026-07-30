"""KB-056 Admin/SOC alert and incident detail and triage endpoints."""

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import require_roles
from app.db.session import fetch_all, fetch_one, fetch_one_write
from app.services.soc_alert_taxonomy import enrich_alert_row
from app.schemas.triage import (
    AlertTriageUpdateRequest,
    IncidentCommentCreateRequest,
    IncidentTriageUpdateRequest,
)

router = APIRouter(prefix="/admin", tags=["admin-triage"])

ADMIN_SOC_ROLES = ("platform_admin", "soc_manager", "soc_analyst")
ALERT_TRIAGE_WRITE_ROLES = ("platform_admin", "soc_manager")


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
            sa.ai_plain_summary,
            sa.ai_technical_summary,
            sa.ai_likely_attack_type,
            sa.ai_business_impact,
            sa.ai_recommended_action,
            sa.ai_false_positive_score,
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
    if "customer_visible" in payload.model_fields_set:
        assignments.append("customer_visible = %s")
        values.append(payload.customer_visible)
    if "ai_plain_summary" in payload.model_fields_set:
        assignments.append("ai_plain_summary = %s")
        values.append(payload.ai_plain_summary)
    if "ai_recommended_action" in payload.model_fields_set:
        assignments.append("ai_recommended_action = %s")
        values.append(payload.ai_recommended_action)
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
