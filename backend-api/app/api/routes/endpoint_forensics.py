"""
Endpoint Forensics & Deception — customer + admin APIs.

Customer payloads use capability labels only (no Velociraptor/Canarytokens brand names).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_current_user, require_roles, require_tenant_match
from app.api.middleware.tier_enforcement import enforce_tenant_subscription_tier
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_all, fetch_one
from app.services import endpoint_forensics_service as efd
from app.services.subscription_tier_service import SubscriptionTier

router = APIRouter(tags=["endpoint-forensics-deception"])


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
            "SELECT id::text, name, short_code, status FROM tenants WHERE id = %s::uuid;",
            (tenant_ref,),
        )
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant
    return _resolve_tenant(tenant_ref)


@router.get("/customer/forensics/{short_code}/summary")
def customer_forensics_summary(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    enforce_tenant_subscription_tier(tenant["id"], SubscriptionTier.PLATINUM, catalog_key="endpoint_forensics_deception")
    summary = efd.get_summary(tenant["id"])
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **summary,
    }


@router.get("/customer/forensics/{short_code}/tripwires")
def customer_forensics_tripwires(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    enforce_tenant_subscription_tier(tenant["id"], SubscriptionTier.PLATINUM, catalog_key="endpoint_forensics_deception")
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "tripwires": efd.list_tripwires(tenant["id"]),
    }


@router.get("/customer/forensics/{short_code}/events")
def customer_forensics_events(
    short_code: str,
    severity: Optional[str] = Query(default=None, max_length=16),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    enforce_tenant_subscription_tier(tenant["id"], SubscriptionTier.PLATINUM, catalog_key="endpoint_forensics_deception")
    rows, total = efd.list_events(
        tenant["id"], severity=severity, page=page, page_size=page_size
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


@router.get("/customer/forensics/{short_code}/collections")
def customer_forensics_collections(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    enforce_tenant_subscription_tier(tenant["id"], SubscriptionTier.PLATINUM, catalog_key="endpoint_forensics_deception")
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "collections": efd.list_collections(tenant["id"]),
    }


@router.post("/admin/forensics/{tenant_ref}/sync")
def admin_forensics_sync(
    tenant_ref: str,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = _resolve_tenant_ref(tenant_ref)
    result = efd.sync_tenant_forensics(tenant["id"])
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **result,
    }


@router.get("/admin/forensics/summary")
def admin_forensics_summary(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT t.short_code, t.name,
               (SELECT count(*)::int FROM tenant_deception_tripwires tw
                WHERE tw.tenant_id = t.id AND tw.deployment_status = 'ACTIVE') AS tripwires,
               (SELECT count(*)::int FROM tenant_deception_events ev
                WHERE ev.tenant_id = t.id AND ev.status IN ('open', 'investigating')) AS open_events,
               (SELECT count(*)::int FROM tenant_forensics_collections fc
                WHERE fc.tenant_id = t.id AND fc.status = 'READY') AS ready_collections
        FROM tenants t
        WHERE t.status = 'active'
        ORDER BY t.short_code;
        """
    ) or []
    return {
        "engine_label": efd.ENGINE_LABEL,
        "tenants": [
            {
                "short_code": r["short_code"],
                "name": r["name"],
                "active_tripwires": int(r.get("tripwires") or 0),
                "open_events": int(r.get("open_events") or 0),
                "ready_collections": int(r.get("ready_collections") or 0),
            }
            for r in rows
        ],
    }
