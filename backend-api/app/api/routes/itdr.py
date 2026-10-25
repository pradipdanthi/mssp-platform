"""
Cloud & Identity Threat Protection (ITDR) — customer + admin APIs.

Customer payloads never include source_ip, raw_details, or engine brand names.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user, require_roles, require_tenant_match
from app.api.middleware.tier_enforcement import enforce_tenant_subscription_tier
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_all, fetch_one
from app.services import itdr_service as itdr
from app.services.subscription_tier_service import SubscriptionTier

router = APIRouter(tags=["cloud-itdr-identity"])

CUSTOMER_ADMIN = ("customer_admin",)


def _resolve_tenant(short_code: str) -> Dict[str, Any]:
    tenant = fetch_one(
        """
        SELECT id::text, name, short_code, status
        FROM tenants
        WHERE short_code = %s;
        """,
        (short_code.upper(),),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


def _resolve_tenant_ref(tenant_ref: str) -> Dict[str, Any]:
    if len(tenant_ref) == 36 and tenant_ref.count("-") == 4:
        tenant = fetch_one(
            """
            SELECT id::text, name, short_code, status
            FROM tenants WHERE id = %s::uuid;
            """,
            (tenant_ref,),
        )
    else:
        tenant = _resolve_tenant(tenant_ref)
        return tenant
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


class ConnectBody(BaseModel):
    provider: str = Field(default="M365_ENTRA", max_length=32)
    tenant_domain: str = Field(min_length=3, max_length=253)
    display_name: Optional[str] = Field(default=None, max_length=200)
    monitored_seat_count: int = Field(default=25, ge=1, le=100000)
    run_sync: bool = True


class RemediateBody(BaseModel):
    """One-click Entra containment. confirm must be true."""

    user_principal_name: str = Field(min_length=3, max_length=320)
    event_id: Optional[str] = Field(default=None, max_length=36)
    revoke_sessions: bool = True
    reset_password: bool = True
    disable_account: bool = True
    confirm: bool = False


@router.get("/customer/itdr/{short_code}/summary")
def customer_itdr_summary(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    enforce_tenant_subscription_tier(tenant["id"], SubscriptionTier.SILVER, catalog_key="cloud_identity_protection")
    summary = itdr.get_summary(tenant["id"])
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **summary,
    }


@router.get("/customer/itdr/{short_code}/events")
def customer_itdr_events(
    short_code: str,
    severity: Optional[str] = Query(default=None, max_length=16),
    event_type: Optional[str] = Query(default=None, max_length=64),
    user: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    enforce_tenant_subscription_tier(tenant["id"], SubscriptionTier.SILVER, catalog_key="cloud_identity_protection")
    rows, total = itdr.list_events(
        tenant["id"],
        severity=severity,
        event_type=event_type,
        user=user,
        page=page,
        page_size=page_size,
    )
    pages = max(1, (total + page_size - 1) // page_size) if total else 1
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "events": rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": pages,
        },
    }


@router.get("/customer/itdr/{short_code}/configs")
def customer_itdr_configs(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    enforce_tenant_subscription_tier(tenant["id"], SubscriptionTier.SILVER, catalog_key="cloud_identity_protection")
    configs = itdr.list_configs(tenant["id"])
    safe = []
    for row in configs:
        provider = row.get("provider")
        if provider == "M365_ENTRA":
            provider_label = "Microsoft 365 / Entra ID"
        elif provider == "AWS_IAM":
            provider_label = "AWS IAM"
        elif provider == "GCP_IAM":
            provider_label = "Google Cloud IAM"
        else:
            provider_label = "Cloud identity"
        safe.append(
            {
                "id": row["id"],
                "provider_label": provider_label,
                "tenant_domain": row["tenant_domain"],
                "display_name": row.get("display_name"),
                "status": row.get("status"),
                "monitored_seat_count": row.get("monitored_seat_count"),
                "last_synced_at": row.get("last_synced_at"),
            }
        )
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "configs": safe,
    }


@router.post("/customer/itdr/{short_code}/connect", status_code=201)
def customer_itdr_connect(
    short_code: str,
    body: ConnectBody,
    current_user: Dict[str, Any] = Depends(require_roles(*CUSTOMER_ADMIN, *ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    enforce_tenant_subscription_tier(tenant["id"], SubscriptionTier.SILVER, catalog_key="cloud_identity_protection")
    try:
        cfg = itdr.connect_provider(
            tenant["id"],
            provider=body.provider,
            tenant_domain=body.tenant_domain,
            display_name=body.display_name,
            monitored_seat_count=body.monitored_seat_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    sync_result = None
    if body.run_sync:
        sync_result = itdr.sync_tenant_itdr(tenant["id"])

    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "config": {
            "id": cfg.get("id"),
            "provider": cfg.get("provider"),
            "tenant_domain": cfg.get("tenant_domain"),
            "status": cfg.get("status"),
            "monitored_seat_count": cfg.get("monitored_seat_count"),
        },
        "sync": sync_result,
        "engine_label": itdr.ENGINE_LABEL,
    }


@router.post("/admin/itdr/{tenant_ref}/sync")
def admin_itdr_sync(
    tenant_ref: str,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = _resolve_tenant_ref(tenant_ref)
    result = itdr.sync_tenant_itdr(tenant["id"])
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **result,
    }


def _run_remediate(
    tenant: Dict[str, Any],
    body: RemediateBody,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        result = itdr.remediate_identity_account(
            tenant["id"],
            user_principal_name=body.user_principal_name,
            event_id=body.event_id,
            revoke_sessions=body.revoke_sessions,
            reset_password=body.reset_password,
            disable_account=body.disable_account,
            actor_user_id=str(current_user.get("id") or "") or None,
            actor_email=str(current_user.get("email") or "") or None,
            actor_role=str(current_user.get("role") or "") or None,
            confirm=body.confirm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        from app.services.itdr_graph_client import ItdrGraphError

        if isinstance(exc, ItdrGraphError):
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=f"Remediation failed: {exc}") from exc
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **result,
    }


@router.post("/customer/itdr/{short_code}/remediate")
def customer_itdr_remediate(
    short_code: str,
    body: RemediateBody,
    current_user: Dict[str, Any] = Depends(require_roles(*CUSTOMER_ADMIN)),
) -> Dict[str, Any]:
    """Customer IT admin one-click: revoke sessions, reset+force change, disable."""
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    enforce_tenant_subscription_tier(tenant["id"], SubscriptionTier.SILVER, catalog_key="cloud_identity_protection")
    return _run_remediate(tenant, body, current_user)


@router.post("/admin/itdr/{tenant_ref}/remediate")
def admin_itdr_remediate(
    tenant_ref: str,
    body: RemediateBody,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """SOC admin one-click Entra containment for a tenant user."""
    tenant = _resolve_tenant_ref(tenant_ref)
    return _run_remediate(tenant, body, current_user)


@router.get("/admin/itdr/summary")
def admin_itdr_summary(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
            t.short_code,
            t.name AS tenant_name,
            COALESCE(c.connected, 0) AS connected_configs,
            COALESCE(c.seats, 0) AS monitored_seats,
            COALESCE(e.open_threats, 0) AS open_threats,
            c.last_synced_at::text AS last_synced_at
        FROM tenants t
        LEFT JOIN LATERAL (
            SELECT
                count(*) FILTER (WHERE status = 'CONNECTED')::int AS connected,
                coalesce(sum(monitored_seat_count) FILTER (WHERE status = 'CONNECTED'), 0)::int AS seats,
                max(last_synced_at) AS last_synced_at
            FROM tenant_cloud_identity_configs cfg
            WHERE cfg.tenant_id = t.id
        ) c ON TRUE
        LEFT JOIN LATERAL (
            SELECT count(*)::int AS open_threats
            FROM tenant_cloud_identity_events ev
            WHERE ev.tenant_id = t.id AND ev.status = 'open'
        ) e ON TRUE
        WHERE t.status = 'active'
        ORDER BY t.name ASC;
        """
    )
    return {"tenants": rows or []}
