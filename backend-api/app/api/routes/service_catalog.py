"""Service Catalog consultation requests + summary (dual portal)."""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.dependencies import require_roles
from app.db.session import db_transaction, fetch_all, fetch_one
from app.services.audit_service import write_audit_event
from app.services.resend_mailer import (
    build_consultation_request_html,
    resend_configured,
    send_resend_email,
)

CUSTOMER_ROLES = ("customer_admin",)
ADMIN_SOC_ROLES = ("platform_admin", "soc_manager", "soc_analyst")
ADMIN_WRITE_ROLES = ("platform_admin", "soc_manager")

router = APIRouter(tags=["service-catalog-consultation"])

SERVICE_KEYS = (
    "log_event_monitoring",
    "incident_response",
    "security_automation",
    "vulnerability_management",
    "continuous_compliance",
    "network_detection_response",
    "threat_intelligence",
    "endpoint_forensics_deception",
    "external_attack_surface",
    "cloud_identity_protection",
    "other",
)

ServiceKey = Literal[
    "log_event_monitoring",
    "incident_response",
    "security_automation",
    "vulnerability_management",
    "continuous_compliance",
    "network_detection_response",
    "threat_intelligence",
    "endpoint_forensics_deception",
    "external_attack_surface",
    "cloud_identity_protection",
    "other",
]

RequestStatus = Literal[
    "PENDING_CONSULTATION",
    "UNDER_REVIEW",
    "APPROVED",
    "PROVISIONED",
    "DECLINED",
    "CLOSED",
]

OPEN_STATUSES = ("PENDING_CONSULTATION", "UNDER_REVIEW")


class ConsultationCreate(BaseModel):
    service_key: ServiceKey
    service_name: str = Field(min_length=2, max_length=200)
    pricing_tier: Optional[str] = Field(default=None, max_length=200)
    endpoint_count: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    m365_seat_count: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    target_domains: List[str] = Field(default_factory=list)
    scope_notes: str = Field(default="", max_length=8000)
    contact_name: Optional[str] = Field(default=None, max_length=200)
    contact_email: Optional[str] = Field(default=None, max_length=320)
    # Admin-on-behalf: required when platform/SOC creates for a tenant
    tenant_short_code: Optional[str] = Field(default=None, max_length=32)


class ConsultationPatch(BaseModel):
    status: Optional[RequestStatus] = None
    admin_notes: Optional[str] = Field(default=None, max_length=8000)


class ConsultationOut(BaseModel):
    id: str
    tenant_id: str
    tenant_name: Optional[str] = None
    short_code: Optional[str] = None
    service_key: str
    service_name: str
    pricing_tier: Optional[str] = None
    endpoint_count: Optional[int] = None
    m365_seat_count: Optional[int] = None
    target_domains: List[str] = Field(default_factory=list)
    scope_notes: str = ""
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    status: str
    admin_notes: Optional[str] = None
    email_dispatched_at: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    requested_by_name: Optional[str] = None


def _admin_base_url() -> str:
    return (os.getenv("ADMIN_PORTAL_BASE_URL") or "http://192.168.0.201:3000").rstrip("/")


def _row_out(row: Dict[str, Any]) -> ConsultationOut:
    domains = row.get("target_domains") or []
    if not isinstance(domains, list):
        domains = list(domains) if domains else []
    return ConsultationOut(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        tenant_name=row.get("tenant_name"),
        short_code=row.get("short_code"),
        service_key=row["service_key"],
        service_name=row["service_name"],
        pricing_tier=row.get("pricing_tier"),
        endpoint_count=row.get("endpoint_count"),
        m365_seat_count=row.get("m365_seat_count"),
        target_domains=[str(d) for d in domains],
        scope_notes=row.get("scope_notes") or "",
        contact_name=row.get("contact_name"),
        contact_email=row.get("contact_email"),
        status=row["status"],
        admin_notes=row.get("admin_notes"),
        email_dispatched_at=str(row["email_dispatched_at"]) if row.get("email_dispatched_at") else None,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
        requested_by_name=row.get("requested_by_name"),
    )


def _resolve_tenant_by_short_code(short_code: str) -> Dict[str, Any]:
    row = fetch_one(
        """
        SELECT id::text, name, short_code
        FROM tenants
        WHERE upper(short_code) = upper(%s)
        LIMIT 1;
        """,
        (short_code.strip(),),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return row


def _resolve_customer_tenant(short_code: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
    tenant = _resolve_tenant_by_short_code(short_code)
    if current_user.get("role") in ("customer_admin", "customer_viewer"):
        user_tenant = current_user.get("tenant_id")
        if not user_tenant or str(user_tenant) != tenant["id"]:
            raise HTTPException(status_code=404, detail="Not found")
    return tenant


def _dispatch_email_async(request_id: str) -> None:
    def _run() -> None:
        row = fetch_one(
            """
            SELECT r.*, t.name AS tenant_name, t.short_code,
                   u.full_name AS requested_by_name, u.email AS requester_email
            FROM service_consultation_requests r
            JOIN tenants t ON t.id = r.tenant_id
            LEFT JOIN platform_users u ON u.id = r.requested_by_user_id
            WHERE r.id = %s::uuid;
            """,
            (request_id,),
        )
        if not row:
            return
        contact_name = row.get("contact_name") or row.get("requested_by_name") or ""
        contact_email = row.get("contact_email") or row.get("requester_email") or ""
        review_url = f"{_admin_base_url()}/service-requests?id={request_id}"
        html = build_consultation_request_html(
            tenant_id=str(row["tenant_id"]),
            tenant_name=row.get("tenant_name") or "",
            short_code=row.get("short_code") or "",
            contact_name=contact_name,
            contact_email=contact_email,
            service_name=row["service_name"],
            pricing_tier=row.get("pricing_tier") or "",
            endpoint_count=row.get("endpoint_count"),
            m365_seat_count=row.get("m365_seat_count"),
            target_domains=list(row.get("target_domains") or []),
            scope_notes=row.get("scope_notes") or "",
            request_id=str(row["id"]),
            admin_review_url=review_url,
        )
        subject = f"[NEW CONSULTING REQUEST] {row['service_name']} - {row.get('tenant_name') or row.get('short_code')}"
        result = send_resend_email(subject=subject, html=html)
        with db_transaction() as cur:
            if result.get("ok"):
                cur.execute(
                    """
                    UPDATE service_consultation_requests
                    SET email_dispatched_at = now(), email_dispatch_error = NULL
                    WHERE id = %s::uuid;
                    """,
                    (request_id,),
                )
            else:
                cur.execute(
                    """
                    UPDATE service_consultation_requests
                    SET email_dispatch_error = %s
                    WHERE id = %s::uuid;
                    """,
                    ((result.get("error") or "send failed")[:800], request_id),
                )

    threading.Thread(target=_run, daemon=True).start()


def _insert_request(
    *,
    tenant_id: str,
    user: Dict[str, Any],
    body: ConsultationCreate,
    submitted_by_admin: bool,
) -> Dict[str, Any]:
    domains = [d.strip() for d in (body.target_domains or []) if d and d.strip()][:50]
    contact_name = (body.contact_name or user.get("full_name") or "").strip() or None
    contact_email = (body.contact_email or user.get("email") or "").strip() or None
    admin_uid = user["id"] if submitted_by_admin else None
    req_uid = None if submitted_by_admin and user.get("user_type") == "platform" else user["id"]
    # If admin submits on behalf, still record the admin as requester when no customer user.
    if req_uid is None:
        req_uid = user["id"]

    with db_transaction() as cur:
        cur.execute(
            """
            INSERT INTO service_consultation_requests (
                tenant_id, requested_by_user_id, submitted_by_admin_user_id,
                service_key, service_name, pricing_tier,
                endpoint_count, m365_seat_count, target_domains, scope_notes,
                contact_name, contact_email, status
            )
            VALUES (
                %s::uuid, %s::uuid, %s::uuid,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, 'PENDING_CONSULTATION'
            )
            RETURNING id::text;
            """,
            (
                tenant_id,
                req_uid,
                admin_uid,
                body.service_key,
                body.service_name.strip(),
                (body.pricing_tier or "").strip() or None,
                body.endpoint_count,
                body.m365_seat_count,
                domains,
                (body.scope_notes or "").strip(),
                contact_name,
                contact_email,
            ),
        )
        new_id = cur.fetchone()["id"]

    write_audit_event(
        action="service_catalog.consultation_requested",
        entity_type="service_consultation_request",
        entity_id=new_id,
        actor_user_id=user.get("id"),
        actor_email=user.get("email"),
        actor_role=user.get("role"),
        tenant_id=tenant_id,
        details={
            "service_key": body.service_key,
            "service_name": body.service_name,
            "on_behalf": submitted_by_admin,
        },
        action_status="SUCCESS",
        resource_type="service_consultation_request",
        resource_id=new_id,
    )
    _dispatch_email_async(new_id)
    row = fetch_one(
        """
        SELECT r.*, t.name AS tenant_name, t.short_code,
               u.full_name AS requested_by_name
        FROM service_consultation_requests r
        JOIN tenants t ON t.id = r.tenant_id
        LEFT JOIN platform_users u ON u.id = r.requested_by_user_id
        WHERE r.id = %s::uuid;
        """,
        (new_id,),
    )
    return row


@router.get("/admin/service-consultation-requests/summary")
def admin_consultation_summary(
    current_user: Dict[str, Any] = Depends(
        require_roles("platform_admin", "soc_manager", "soc_analyst")
    ),
) -> Dict[str, Any]:
    row = fetch_one(
        """
        SELECT
          COUNT(*) FILTER (WHERE status = 'PENDING_CONSULTATION')::int AS pending_consultation,
          COUNT(*) FILTER (WHERE status = 'UNDER_REVIEW')::int AS under_review,
          COUNT(*) FILTER (WHERE status IN ('PENDING_CONSULTATION', 'UNDER_REVIEW'))::int AS unreviewed_total
        FROM service_consultation_requests;
        """
    )
    return {
        "pending_consultation": int((row or {}).get("pending_consultation") or 0),
        "under_review": int((row or {}).get("under_review") or 0),
        "unreviewed_total": int((row or {}).get("unreviewed_total") or 0),
        "resend_configured": resend_configured(),
    }


@router.get("/admin/service-consultation-requests")
def admin_list_consultations(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: Dict[str, Any] = Depends(
        require_roles("platform_admin", "soc_manager", "soc_analyst")
    ),
) -> Dict[str, Any]:
    if status_filter:
        rows = fetch_all(
            """
            SELECT r.*, t.name AS tenant_name, t.short_code,
                   u.full_name AS requested_by_name
            FROM service_consultation_requests r
            JOIN tenants t ON t.id = r.tenant_id
            LEFT JOIN platform_users u ON u.id = r.requested_by_user_id
            WHERE r.status = %s
            ORDER BY r.created_at DESC
            LIMIT 500;
            """,
            (status_filter,),
        )
    else:
        rows = fetch_all(
            """
            SELECT r.*, t.name AS tenant_name, t.short_code,
                   u.full_name AS requested_by_name
            FROM service_consultation_requests r
            JOIN tenants t ON t.id = r.tenant_id
            LEFT JOIN platform_users u ON u.id = r.requested_by_user_id
            ORDER BY
              CASE r.status
                WHEN 'PENDING_CONSULTATION' THEN 0
                WHEN 'UNDER_REVIEW' THEN 1
                WHEN 'APPROVED' THEN 2
                ELSE 3
              END,
              r.created_at DESC
            LIMIT 500;
            """
        )
    return {"requests": [_row_out(r).model_dump() for r in rows]}


@router.patch("/admin/service-consultation-requests/{request_id}")
def admin_patch_consultation(
    request_id: UUID,
    body: ConsultationPatch,
    current_user: Dict[str, Any] = Depends(require_roles("platform_admin", "soc_manager")),
) -> ConsultationOut:
    existing = fetch_one(
        "SELECT id::text FROM service_consultation_requests WHERE id = %s::uuid;",
        (str(request_id),),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Request not found")
    if body.status is None and body.admin_notes is None:
        raise HTTPException(status_code=400, detail="No changes provided")
    with db_transaction() as cur:
        if body.status is not None:
            cur.execute(
                """
                UPDATE service_consultation_requests
                SET status = %s,
                    admin_notes = COALESCE(%s, admin_notes)
                WHERE id = %s::uuid;
                """,
                (body.status, body.admin_notes, str(request_id)),
            )
        else:
            cur.execute(
                """
                UPDATE service_consultation_requests
                SET admin_notes = %s
                WHERE id = %s::uuid;
                """,
                (body.admin_notes, str(request_id)),
            )
    write_audit_event(
        action="service_catalog.consultation_updated",
        entity_type="service_consultation_request",
        entity_id=str(request_id),
        actor_user_id=current_user.get("id"),
        actor_email=current_user.get("email"),
        actor_role=current_user.get("role"),
        details={"status": body.status, "has_notes": body.admin_notes is not None},
        action_status="SUCCESS",
        resource_type="service_consultation_request",
        resource_id=str(request_id),
    )
    row = fetch_one(
        """
        SELECT r.*, t.name AS tenant_name, t.short_code,
               u.full_name AS requested_by_name
        FROM service_consultation_requests r
        JOIN tenants t ON t.id = r.tenant_id
        LEFT JOIN platform_users u ON u.id = r.requested_by_user_id
        WHERE r.id = %s::uuid;
        """,
        (str(request_id),),
    )
    return _row_out(row)


@router.post("/admin/service-consultation-requests", status_code=status.HTTP_201_CREATED)
def admin_create_consultation(
    body: ConsultationCreate,
    current_user: Dict[str, Any] = Depends(require_roles("platform_admin", "soc_manager")),
) -> ConsultationOut:
    if not body.tenant_short_code:
        raise HTTPException(status_code=400, detail="tenant_short_code is required")
    tenant = _resolve_tenant_by_short_code(body.tenant_short_code)
    row = _insert_request(
        tenant_id=tenant["id"],
        user=current_user,
        body=body,
        submitted_by_admin=True,
    )
    return _row_out(row)


@router.post(
    "/customer/service-consultation-requests/{short_code}",
    status_code=status.HTTP_201_CREATED,
)
def customer_create_consultation(
    short_code: str,
    body: ConsultationCreate,
    current_user: Dict[str, Any] = Depends(require_roles(*CUSTOMER_ROLES, *ADMIN_WRITE_ROLES)),
) -> ConsultationOut:
    tenant = _resolve_customer_tenant(short_code, current_user)
    # Block duplicate open requests for same service
    dup = fetch_one(
        """
        SELECT id::text FROM service_consultation_requests
        WHERE tenant_id = %s::uuid
          AND service_key = %s
          AND status = ANY(%s)
        LIMIT 1;
        """,
        (tenant["id"], body.service_key, list(OPEN_STATUSES)),
    )
    if dup:
        raise HTTPException(
            status_code=409,
            detail="An open consultation request already exists for this service.",
        )
    on_behalf = current_user.get("role") in ADMIN_WRITE_ROLES
    row = _insert_request(
        tenant_id=tenant["id"],
        user=current_user,
        body=body,
        submitted_by_admin=on_behalf,
    )
    return _row_out(row)


@router.get("/customer/service-consultation-requests/{short_code}")
def customer_list_consultations(
    short_code: str,
    current_user: Dict[str, Any] = Depends(
        require_roles(*CUSTOMER_ROLES, "customer_viewer", *ADMIN_SOC_ROLES)
    ),
) -> Dict[str, Any]:
    tenant = _resolve_customer_tenant(short_code, current_user)
    rows = fetch_all(
        """
        SELECT r.*, t.name AS tenant_name, t.short_code,
               u.full_name AS requested_by_name
        FROM service_consultation_requests r
        JOIN tenants t ON t.id = r.tenant_id
        LEFT JOIN platform_users u ON u.id = r.requested_by_user_id
        WHERE r.tenant_id = %s::uuid
        ORDER BY r.created_at DESC
        LIMIT 200;
        """,
        (tenant["id"],),
    )
    # Customer-safe: strip admin_notes
    out = []
    for r in rows:
        item = _row_out(r).model_dump()
        item.pop("admin_notes", None)
        out.append(item)
    return {"requests": out}
