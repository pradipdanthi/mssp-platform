"""Service Catalog consultation requests + summary (dual portal)."""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.dependencies import require_roles
from app.db.session import db_transaction, fetch_all, fetch_one, fetch_one_write
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
    tenant_id: Optional[UUID] = Query(default=None),
    current_user: Dict[str, Any] = Depends(
        require_roles("platform_admin", "soc_manager", "soc_analyst")
    ),
) -> Dict[str, Any]:
    tid = str(tenant_id) if tenant_id else None
    where = "WHERE tenant_id = %s::uuid" if tid else ""
    params: tuple = (tid,) if tid else ()
    row = fetch_one(
        f"""
        SELECT
          COUNT(*) FILTER (WHERE status = 'PENDING_CONSULTATION')::int AS pending_consultation,
          COUNT(*) FILTER (WHERE status = 'UNDER_REVIEW')::int AS under_review,
          COUNT(*) FILTER (WHERE status IN ('PENDING_CONSULTATION', 'UNDER_REVIEW'))::int AS unreviewed_total
        FROM service_consultation_requests
        {where};
        """,
        params,
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
    service_key: Optional[str] = Query(default=None),
    tenant_id: Optional[UUID] = Query(default=None),
    current_user: Dict[str, Any] = Depends(
        require_roles("platform_admin", "soc_manager", "soc_analyst")
    ),
) -> Dict[str, Any]:
    clauses: List[str] = []
    params: List[Any] = []
    if status_filter:
        clauses.append("r.status = %s")
        params.append(status_filter)
    if service_key:
        if service_key not in SERVICE_KEYS:
            raise HTTPException(status_code=400, detail="Unknown service_key.")
        clauses.append("r.service_key = %s")
        params.append(service_key)
    if tenant_id is not None:
        clauses.append("r.tenant_id = %s")
        params.append(tenant_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = fetch_all(
        f"""
        SELECT r.*, t.name AS tenant_name, t.short_code,
               u.full_name AS requested_by_name
        FROM service_consultation_requests r
        JOIN tenants t ON t.id = r.tenant_id
        LEFT JOIN platform_users u ON u.id = r.requested_by_user_id
        {where}
        ORDER BY
          CASE r.status
            WHEN 'PENDING_CONSULTATION' THEN 0
            WHEN 'UNDER_REVIEW' THEN 1
            WHEN 'APPROVED' THEN 2
            ELSE 3
          END,
          r.created_at DESC
        LIMIT 500;
        """,
        tuple(params),
    )
    return {"requests": [_row_out(r).model_dump() for r in rows]}


@router.patch("/admin/service-consultation-requests/{request_id}")
def admin_patch_consultation(
    request_id: UUID,
    body: ConsultationPatch,
    current_user: Dict[str, Any] = Depends(require_roles("platform_admin", "soc_manager")),
) -> ConsultationOut:
    existing = fetch_one(
        """
        SELECT id::text, tenant_id::text, service_key, status
        FROM service_consultation_requests WHERE id = %s::uuid;
        """,
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

    entitlement_sync: Dict[str, Any] = {}
    if body.status == "APPROVED":
        from app.services.tenant_entitlement_defaults import (
            enable_entitlement_for_catalog_key,
            trigger_post_enable_sync,
        )

        enabled = enable_entitlement_for_catalog_key(
            existing["tenant_id"],
            existing["service_key"],
        )
        if enabled is not None:
            entitlement_sync = trigger_post_enable_sync(
                existing["tenant_id"],
                existing["service_key"],
            )
            entitlement_sync["entitlement_enabled"] = True
        else:
            entitlement_sync = {
                "entitlement_enabled": False,
                "note": "No auto-entitlement mapping for this service key",
            }

    write_audit_event(
        action="service_catalog.consultation_updated",
        entity_type="service_consultation_request",
        entity_id=str(request_id),
        actor_user_id=current_user.get("id"),
        actor_email=current_user.get("email"),
        actor_role=current_user.get("role"),
        tenant_id=existing.get("tenant_id"),
        details={
            "status": body.status,
            "service_key": existing.get("service_key"),
            "has_notes": body.admin_notes is not None,
            "entitlement_sync": entitlement_sync or None,
        },
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


# ---------------------------------------------------------------------------
# Admin Service Catalog (pricing + adoption + rollout)
# ---------------------------------------------------------------------------

class CatalogPricingPatch(BaseModel):
    pricing_display: str = Field(min_length=1, max_length=200)
    pricing_notes: Optional[str] = Field(default=None, max_length=2000)
    competitor_value: Optional[str] = Field(default=None, max_length=400)


class CatalogRolloutRequest(BaseModel):
    tenant_ids: List[UUID] = Field(min_length=1, max_length=200)
    admin_notes: Optional[str] = Field(default=None, max_length=2000)
    mark_requests_approved: bool = True
    action: Literal["enable", "disable"] = "enable"
    customer_order_number: str = Field(min_length=1, max_length=80)
    confirmation_email: str = Field(min_length=5, max_length=200)
    asset_ids: List[UUID] = Field(default_factory=list, max_length=2000)


def _ensure_pricing_seeded() -> None:
    """Idempotent seed when migration not yet applied on long-lived DB."""
    from app.db.session import execute
    from app.services.service_catalog_pricing import CATALOG_DEFAULTS

    try:
        existing = fetch_one("SELECT COUNT(*)::int AS n FROM service_catalog_pricing;")
    except Exception:
        return
    if existing and int(existing.get("n") or 0) > 0:
        return
    for row in CATALOG_DEFAULTS:
        execute(
            """
            INSERT INTO service_catalog_pricing (
              service_key, service_name, pricing_display, competitor_value,
              is_core, requestable, sort_order
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (service_key) DO NOTHING;
            """,
            (
                row["service_key"],
                row["service_name"],
                row["pricing_display"],
                row.get("competitor_value"),
                row["is_core"],
                row["requestable"],
                row["sort_order"],
            ),
        )


def _open_request_count(service_key: str) -> int:
    row = fetch_one(
        """
        SELECT COUNT(*)::int AS n
        FROM service_consultation_requests
        WHERE service_key = %s
          AND status IN ('PENDING_CONSULTATION', 'UNDER_REVIEW');
        """,
        (service_key,),
    )
    return int((row or {}).get("n") or 0)


def _adoption_count(service_key: str) -> int:
    from app.services.service_catalog_pricing import ADOPTION_SQL

    pred = ADOPTION_SQL.get(service_key)
    if not pred:
        return 0
    sql_frag, _ = pred
    row = fetch_one(
        f"""
        SELECT COUNT(*)::int AS n
        FROM tenants t
        LEFT JOIN tenant_entitlements e ON e.tenant_id = t.id
        WHERE {sql_frag};
        """
    )
    return int((row or {}).get("n") or 0)


def _open_requests_for_service(service_key: str, limit: int = 8) -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT r.id::text, r.tenant_id::text, t.name AS tenant_name, t.short_code,
               r.status, r.created_at::text, r.requested_by_user_id::text,
               u.full_name AS requested_by_name
        FROM service_consultation_requests r
        JOIN tenants t ON t.id = r.tenant_id
        LEFT JOIN platform_users u ON u.id = r.requested_by_user_id
        WHERE r.service_key = %s
          AND r.status IN ('PENDING_CONSULTATION', 'UNDER_REVIEW')
        ORDER BY r.created_at DESC
        LIMIT %s;
        """,
        (service_key, limit),
    )
    return [
        {
            "id": r["id"],
            "tenant_id": r["tenant_id"],
            "tenant_name": r.get("tenant_name"),
            "short_code": r.get("short_code"),
            "status": r.get("status"),
            "created_at": r.get("created_at"),
            "requested_by_name": r.get("requested_by_name"),
        }
        for r in rows
    ]


@router.get("/admin/service-catalog")
def admin_service_catalog(
    current_user: Dict[str, Any] = Depends(
        require_roles("platform_admin", "soc_manager", "soc_analyst")
    ),
) -> Dict[str, Any]:
    from app.services.service_catalog_pricing import CATALOG_DEFAULTS

    _ensure_pricing_seeded()
    try:
        rows = fetch_all(
            """
            SELECT service_key, service_name, pricing_display, pricing_notes,
                   competitor_value, is_core, requestable, sort_order,
                   updated_at::text, updated_by::text
            FROM service_catalog_pricing
            ORDER BY sort_order ASC, service_key ASC;
            """
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Service catalog pricing table missing. Apply postgres/init/033_service_catalog_pricing.sql.",
        ) from exc

    by_key = {r["service_key"]: r for r in rows}
    services: List[Dict[str, Any]] = []
    for default in CATALOG_DEFAULTS:
        key = default["service_key"]
        row = by_key.get(key) or default
        open_reqs = _open_requests_for_service(key)
        services.append(
            {
                "service_key": key,
                "service_name": row.get("service_name") or default["service_name"],
                "pricing_display": row.get("pricing_display") or default["pricing_display"],
                "pricing_notes": row.get("pricing_notes"),
                "competitor_value": row.get("competitor_value")
                if row.get("competitor_value") is not None
                else default.get("competitor_value"),
                "is_core": bool(row.get("is_core", default["is_core"])),
                "requestable": bool(row.get("requestable", default["requestable"])),
                "sort_order": int(row.get("sort_order") or default["sort_order"]),
                "updated_at": row.get("updated_at"),
                "active_tenant_count": _adoption_count(key),
                "open_request_count": _open_request_count(key),
                "open_requests": open_reqs,
                "rollout_supported": key
                in (
                    "security_automation",
                    "vulnerability_management",
                    "continuous_compliance",
                    "external_attack_surface",
                    "cloud_identity_protection",
                    "network_detection_response",
                    "threat_intelligence",
                    "endpoint_forensics_deception",
                ),
            }
        )

    return {"services": services}


@router.get("/customer/service-catalog/pricing")
def customer_service_catalog_pricing(
    current_user: Dict[str, Any] = Depends(
        require_roles(*CUSTOMER_ROLES, "customer_viewer", *ADMIN_SOC_ROLES)
    ),
) -> Dict[str, Any]:
    """Customer-safe pricing overlay for the Service Catalog UI."""
    from app.services.service_catalog_pricing import CATALOG_DEFAULTS

    _ensure_pricing_seeded()
    try:
        rows = fetch_all(
            """
            SELECT service_key, pricing_display, competitor_value
            FROM service_catalog_pricing;
            """
        )
    except Exception:
        rows = []
    by_key = {r["service_key"]: r for r in rows}
    items = []
    for default in CATALOG_DEFAULTS:
        key = default["service_key"]
        row = by_key.get(key) or {}
        items.append(
            {
                "service_key": key,
                "pricing_display": row.get("pricing_display") or default["pricing_display"],
                "competitor_value": row.get("competitor_value")
                if row.get("competitor_value") is not None
                else default.get("competitor_value"),
            }
        )
    return {"pricing": items}


@router.patch("/admin/service-catalog/{service_key}/pricing")
def admin_patch_catalog_pricing(
    service_key: str,
    body: CatalogPricingPatch,
    current_user: Dict[str, Any] = Depends(require_roles("platform_admin", "soc_manager")),
) -> Dict[str, Any]:
    from app.services.service_catalog_pricing import default_for

    if service_key not in SERVICE_KEYS or service_key == "other":
        raise HTTPException(status_code=404, detail="Unknown catalog service.")
    _ensure_pricing_seeded()
    base = default_for(service_key) or {"service_name": service_key}
    before = fetch_one(
        "SELECT pricing_display FROM service_catalog_pricing WHERE service_key = %s;",
        (service_key,),
    )
    row = fetch_one(
        """
        INSERT INTO service_catalog_pricing (
          service_key, service_name, pricing_display, pricing_notes, competitor_value,
          is_core, requestable, sort_order, updated_at, updated_by
        ) VALUES (
          %s, %s, %s, %s, %s, %s, %s, %s, now(), %s::uuid
        )
        ON CONFLICT (service_key) DO UPDATE SET
          pricing_display = EXCLUDED.pricing_display,
          pricing_notes = EXCLUDED.pricing_notes,
          competitor_value = EXCLUDED.competitor_value,
          updated_at = now(),
          updated_by = EXCLUDED.updated_by
        RETURNING service_key, service_name, pricing_display, pricing_notes,
                  competitor_value, is_core, requestable, sort_order,
                  updated_at::text, updated_by::text;
        """,
        (
            service_key,
            base.get("service_name") or service_key,
            body.pricing_display.strip(),
            (body.pricing_notes or "").strip() or None,
            (body.competitor_value if body.competitor_value is not None else base.get("competitor_value")),
            bool(base.get("is_core")),
            bool(base.get("requestable", True)),
            int(base.get("sort_order") or 100),
            current_user["id"],
        ),
    )
    write_audit_event(
        actor_user_id=current_user["id"],
        action="service_catalog.pricing_updated",
        entity_type="service_catalog_pricing",
        entity_id=service_key,
        details={
            "before": (before or {}).get("pricing_display"),
            "after": body.pricing_display.strip(),
        },
        actor_role=current_user.get("role"),
        resource_type="service_catalog_pricing",
        resource_id=service_key,
    )
    return dict(row or {})


@router.post("/admin/service-catalog/{service_key}/rollout")
def admin_rollout_catalog_service(
    service_key: str,
    body: CatalogRolloutRequest,
    current_user: Dict[str, Any] = Depends(require_roles("platform_admin", "soc_manager")),
) -> Dict[str, Any]:
    from app.services.appliance_entitlement_sync import (
        appliance_ids_for_assets,
        enqueue_tenant_entitlement_jobs,
    )
    from app.services.asset_service_coverage import replace_coverage
    from app.services.tenant_entitlement_defaults import (
        CATALOG_KEY_TO_ENTITLEMENT_UPDATES,
        disable_entitlement_for_catalog_key,
        enable_entitlement_for_catalog_key,
        trigger_post_enable_sync,
    )

    if service_key not in CATALOG_KEY_TO_ENTITLEMENT_UPDATES:
        raise HTTPException(
            status_code=400,
            detail="This service is Core or cannot be rolled out via entitlements.",
        )
    order_number = body.customer_order_number.strip()
    confirm_email = body.confirmation_email.strip()
    if "@" not in confirm_email or "." not in confirm_email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="confirmation_email is not a valid email.")
    if body.action not in ("enable", "disable"):
        raise HTTPException(status_code=400, detail="action must be enable or disable.")
    if len(body.tenant_ids) > 1 and body.asset_ids:
        raise HTTPException(
            status_code=400,
            detail="Asset-level rollout can target one customer at a time.",
        )

    results: List[Dict[str, Any]] = []
    for tid in body.tenant_ids:
        tenant = fetch_one(
            "SELECT id::text, name, short_code FROM tenants WHERE id = %s::uuid;",
            (str(tid),),
        )
        if not tenant:
            results.append({"tenant_id": str(tid), "ok": False, "error": "tenant_not_found"})
            continue
        try:
            asset_ids = [str(a) for a in body.asset_ids]
            scope = "assets" if asset_ids else "account"
            from app.services.asset_service_coverage import list_covered_asset_ids

            if body.action == "enable":
                enable_entitlement_for_catalog_key(str(tid), service_key)
                if asset_ids:
                    replace_coverage(
                        tenant_id=str(tid),
                        service_key=service_key,
                        asset_ids=asset_ids,
                        actor_user_id=current_user.get("id"),
                    )
                sync_detail = trigger_post_enable_sync(str(tid), service_key)
            elif asset_ids:
                current = list_covered_asset_ids(str(tid), service_key)
                drop = set(asset_ids)
                remaining = [aid for aid in current if aid not in drop]
                replace_coverage(
                    tenant_id=str(tid),
                    service_key=service_key,
                    asset_ids=remaining,
                    actor_user_id=current_user.get("id"),
                )
                if not remaining:
                    disable_entitlement_for_catalog_key(str(tid), service_key)
                sync_detail = {
                    "catalog_key": service_key,
                    "synced": True,
                    "action": "disable_assets",
                    "remaining": len(remaining),
                }
            else:
                disable_entitlement_for_catalog_key(str(tid), service_key)
                replace_coverage(
                    tenant_id=str(tid),
                    service_key=service_key,
                    asset_ids=[],
                    actor_user_id=current_user.get("id"),
                )
                sync_detail = {"catalog_key": service_key, "synced": True, "action": "disable"}

            appliance_filter = appliance_ids_for_assets(str(tid), asset_ids) if asset_ids else None
            job_info = enqueue_tenant_entitlement_jobs(
                tenant_id=str(tid),
                catalog_key=service_key,
                action=body.action,
                actor_user_id=current_user.get("id"),
                order_number=order_number,
                asset_ids=asset_ids,
                appliance_ids=appliance_filter or None,
            )
            approved = 0
            if body.action == "enable" and body.mark_requests_approved:
                with db_transaction() as cur:
                    cur.execute(
                        """
                        UPDATE service_consultation_requests
                        SET status = 'APPROVED',
                            admin_notes = COALESCE(%s, admin_notes),
                            updated_at = now()
                        WHERE tenant_id = %s::uuid
                          AND service_key = %s
                          AND status IN ('PENDING_CONSULTATION', 'UNDER_REVIEW');
                        """,
                        (body.admin_notes, str(tid), service_key),
                    )
                    approved = cur.rowcount or 0

            order_row = fetch_one_write(
                """
                INSERT INTO service_rollout_orders (
                    tenant_id, service_key, action, scope, customer_order_number,
                    confirmation_email, asset_ids, requested_by_user_id, admin_notes, jobs_queued
                )
                VALUES (
                    %s::uuid, %s, %s, %s, %s, %s, %s::uuid[], %s::uuid, %s, %s
                )
                RETURNING id::text;
                """,
                (
                    str(tid),
                    service_key,
                    body.action,
                    scope,
                    order_number,
                    confirm_email,
                    asset_ids,
                    current_user.get("id"),
                    body.admin_notes,
                    int(job_info.get("jobs_queued") or 0),
                ),
            )
            html = (
                "<p>This confirms a controlled service change on your MSSP account.</p>"
                f"<p><strong>Order:</strong> {order_number}<br>"
                f"<strong>Customer:</strong> {tenant.get('name')} ({tenant.get('short_code')})<br>"
                f"<strong>Service:</strong> {service_key}<br>"
                f"<strong>Action:</strong> {body.action}<br>"
                f"<strong>Scope:</strong> {scope}"
                f"{' · ' + str(len(asset_ids)) + ' asset(s)' if asset_ids else ''}</p>"
            )
            mail = send_resend_email(
                subject=f"[SERVICE {body.action.upper()}] {service_key} · {order_number}",
                html=html,
                to=[confirm_email],
            )
            if order_row:
                with db_transaction() as cur:
                    if mail.get("ok"):
                        cur.execute(
                            """
                            UPDATE service_rollout_orders
                            SET email_dispatched_at = now(), email_dispatch_error = NULL
                            WHERE id = %s::uuid;
                            """,
                            (order_row["id"],),
                        )
                    else:
                        cur.execute(
                            """
                            UPDATE service_rollout_orders
                            SET email_dispatch_error = %s
                            WHERE id = %s::uuid;
                            """,
                            ((mail.get("error") or "send_failed")[:500], order_row["id"]),
                        )

            write_audit_event(
                actor_user_id=current_user["id"],
                action="service_catalog.rollout",
                entity_type="tenant",
                entity_id=str(tid),
                details={
                    "service_key": service_key,
                    "action": body.action,
                    "order_number": order_number,
                    "scope": scope,
                    "assets": len(asset_ids),
                    "approved_open_requests": approved,
                    "sync": sync_detail,
                    "jobs": job_info,
                    "email_ok": bool(mail.get("ok")),
                },
                tenant_id=str(tid),
                actor_role=current_user.get("role"),
                resource_type="service_catalog_rollout",
                resource_id=service_key,
            )
            results.append(
                {
                    "tenant_id": str(tid),
                    "tenant_name": tenant.get("name"),
                    "short_code": tenant.get("short_code"),
                    "ok": True,
                    "approved_open_requests": approved,
                    "jobs_queued": job_info.get("jobs_queued"),
                    "service_ids": job_info.get("service_ids"),
                    "order_id": (order_row or {}).get("id"),
                    "email_ok": bool(mail.get("ok")),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "tenant_id": str(tid),
                    "tenant_name": tenant.get("name"),
                    "short_code": tenant.get("short_code"),
                    "ok": False,
                    "error": str(exc)[:240],
                }
            )

    return {
        "service_key": service_key,
        "action": body.action,
        "rolled_out": sum(1 for r in results if r.get("ok")),
        "failed": sum(1 for r in results if not r.get("ok")),
        "results": results,
    }
