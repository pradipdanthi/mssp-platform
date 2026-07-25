"""
KB-066: Admin recommendation management (GET one, POST, PATCH).

List remains on GET /admin/recommendations in admin.py (KB-062).
Write roles match alert triage: platform_admin + soc_manager.
"""

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import require_roles
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_one, fetch_one_write
from app.schemas.recommendations_admin import (
    RecommendationCreateRequest,
    RecommendationDetail,
    RecommendationUpdateRequest,
)

router = APIRouter(prefix="/admin/recommendations", tags=["admin-recommendations"])

RECOMMENDATION_WRITE_ROLES = ("platform_admin", "soc_manager")


def _fetch_recommendation_detail(recommendation_id: UUID) -> Optional[Dict[str, Any]]:
    return fetch_one(
        """
        SELECT
            cr.id::text,
            cr.tenant_id::text,
            t.name AS tenant_name,
            t.short_code,
            cr.title,
            cr.description,
            cr.priority,
            cr.category,
            cr.status,
            cr.customer_visible,
            cr.due_at::text,
            cr.completed_at::text,
            cr.related_alert_id::text,
            cr.related_incident_id::text,
            cr.related_vulnerability_id::text,
            cr.created_at::text,
            cr.updated_at::text
        FROM customer_recommendations cr
        JOIN tenants t ON t.id = cr.tenant_id
        WHERE cr.id = %s;
        """,
        (str(recommendation_id),),
    )


@router.get("/{recommendation_id}", response_model=RecommendationDetail)
def get_recommendation_detail(
    recommendation_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    row = _fetch_recommendation_detail(recommendation_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    return row


@router.post("", response_model=RecommendationDetail, status_code=status.HTTP_201_CREATED)
def create_recommendation(
    payload: RecommendationCreateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*RECOMMENDATION_WRITE_ROLES)),
) -> Dict[str, Any]:
    tenant = fetch_one("SELECT id FROM tenants WHERE id = %s;", (str(payload.tenant_id),))
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="tenant_id does not reference an existing tenant",
        )

    if payload.related_alert_id is not None:
        alert = fetch_one(
            "SELECT id FROM security_alerts WHERE id = %s AND tenant_id = %s;",
            (str(payload.related_alert_id), str(payload.tenant_id)),
        )
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="related_alert_id not found for this tenant",
            )

    if payload.related_incident_id is not None:
        incident = fetch_one(
            "SELECT id FROM incidents WHERE id = %s AND tenant_id = %s;",
            (str(payload.related_incident_id), str(payload.tenant_id)),
        )
        if not incident:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="related_incident_id not found for this tenant",
            )

    if payload.status == "completed":
        created = fetch_one_write(
            """
            INSERT INTO customer_recommendations (
                tenant_id, related_alert_id, related_incident_id,
                title, description, priority, category, status,
                customer_visible, due_at, completed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            RETURNING id::text;
            """,
            (
                str(payload.tenant_id),
                str(payload.related_alert_id) if payload.related_alert_id else None,
                str(payload.related_incident_id) if payload.related_incident_id else None,
                payload.title.strip(),
                payload.description.strip(),
                payload.priority,
                payload.category.strip(),
                payload.status,
                payload.customer_visible,
                payload.due_at,
            ),
        )
    else:
        created = fetch_one_write(
            """
            INSERT INTO customer_recommendations (
                tenant_id, related_alert_id, related_incident_id,
                title, description, priority, category, status,
                customer_visible, due_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id::text;
            """,
            (
                str(payload.tenant_id),
                str(payload.related_alert_id) if payload.related_alert_id else None,
                str(payload.related_incident_id) if payload.related_incident_id else None,
                payload.title.strip(),
                payload.description.strip(),
                payload.priority,
                payload.category.strip(),
                payload.status,
                payload.customer_visible,
                payload.due_at,
            ),
        )

    row = _fetch_recommendation_detail(UUID(created["id"]))
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Recommendation creation failed",
        )
    return row


@router.patch("/{recommendation_id}", response_model=RecommendationDetail)
def update_recommendation(
    recommendation_id: UUID,
    payload: RecommendationUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*RECOMMENDATION_WRITE_ROLES)),
) -> Dict[str, Any]:
    existing = _fetch_recommendation_detail(recommendation_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    fields = []
    params: list = []

    for field_name in (
        "title",
        "description",
        "priority",
        "category",
        "status",
        "customer_visible",
        "due_at",
        "completed_at",
        "related_alert_id",
        "related_incident_id",
    ):
        if field_name not in payload.model_fields_set:
            continue
        value = getattr(payload, field_name)
        if field_name in ("title", "description", "category") and value is not None:
            value = value.strip()
        if field_name in ("related_alert_id", "related_incident_id"):
            value = str(value) if value is not None else None
        fields.append(f"{field_name} = %s")
        params.append(value)

    # Auto-stamp completed_at when moving to completed and caller did not set it.
    if (
        "status" in payload.model_fields_set
        and payload.status == "completed"
        and "completed_at" not in payload.model_fields_set
    ):
        fields.append("completed_at = now()")

    if not fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one field must be provided",
        )

    params.append(str(recommendation_id))
    updated = fetch_one_write(
        f"UPDATE customer_recommendations SET {', '.join(fields)} WHERE id = %s RETURNING id::text;",
        tuple(params),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    row = _fetch_recommendation_detail(UUID(updated["id"]))
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Recommendation update failed",
        )
    return row
