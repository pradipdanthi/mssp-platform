"""
Network Detection & Response (NDR) — customer + admin APIs.

Customer payloads never include raw IPs, vendor names, or raw_details.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_current_user, require_roles, require_tenant_match
from app.api.middleware.tier_enforcement import enforce_tenant_subscription_tier
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_all, fetch_one
from app.services import ndr_service as ndr
from app.services.subscription_tier_service import SubscriptionTier

router = APIRouter(tags=["ndr-network-detection"])


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


def _sensor_type_label(raw: Optional[str]) -> str:
    key = (raw or "").upper()
    if key == "SURICATA_ZEEK_HYBRID":
        return "Hybrid signature + metadata sensor"
    if key == "SIGNATURE":
        return "Signature sensor"
    if key == "METADATA":
        return "Metadata sensor"
    return "Network sensor"


@router.get("/customer/ndr/{short_code}/summary")
def customer_ndr_summary(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    enforce_tenant_subscription_tier(tenant["id"], SubscriptionTier.PLATINUM)
    summary = ndr.get_summary(tenant["id"])
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **summary,
    }


@router.get("/customer/ndr/{short_code}/events")
def customer_ndr_events(
    short_code: str,
    severity: Optional[str] = Query(default=None, max_length=16),
    event_category: Optional[str] = Query(default=None, max_length=64),
    protocol: Optional[str] = Query(default=None, max_length=16),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    enforce_tenant_subscription_tier(tenant["id"], SubscriptionTier.PLATINUM)
    rows, total = ndr.list_events(
        tenant["id"],
        severity=severity,
        event_category=event_category,
        protocol=protocol,
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


@router.get("/customer/ndr/{short_code}/sensors")
def customer_ndr_sensors(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    enforce_tenant_subscription_tier(tenant["id"], SubscriptionTier.PLATINUM)
    sensors = []
    for row in ndr.list_sensors(tenant["id"]):
        sensors.append(
            {
                "id": row["id"],
                "sensor_name": row.get("sensor_name"),
                "sensor_status": row.get("sensor_status"),
                "sensor_type_label": _sensor_type_label(row.get("sensor_type")),
                "capture_interface": row.get("capture_interface"),
                "flows_observed": row.get("flows_observed"),
                "bytes_observed": row.get("bytes_observed"),
                "last_heartbeat": row.get("last_heartbeat"),
            }
        )
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "sensors": sensors,
    }


@router.post("/admin/ndr/{tenant_ref}/sync")
def admin_ndr_sync(
    tenant_ref: str,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = _resolve_tenant_ref(tenant_ref)
    result = ndr.sync_tenant_ndr(tenant["id"])
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **result,
    }


@router.get("/admin/ndr/summary")
def admin_ndr_summary(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
            t.short_code,
            t.name AS tenant_name,
            COALESCE(s.sensor_count, 0) AS sensor_count,
            COALESCE(s.online_sensors, 0) AS online_sensors,
            COALESCE(e.open_events, 0) AS open_events,
            s.last_heartbeat::text AS last_heartbeat
        FROM tenants t
        LEFT JOIN LATERAL (
            SELECT
                count(*)::int AS sensor_count,
                count(*) FILTER (WHERE sensor_status = 'ONLINE')::int AS online_sensors,
                max(last_heartbeat) AS last_heartbeat
            FROM tenant_ndr_sensors ns
            WHERE ns.tenant_id = t.id
        ) s ON TRUE
        LEFT JOIN LATERAL (
            SELECT count(*)::int AS open_events
            FROM tenant_ndr_events ne
            WHERE ne.tenant_id = t.id AND ne.status = 'open'
        ) e ON TRUE
        WHERE t.status = 'active'
        ORDER BY t.name ASC;
        """
    )
    return {"tenants": rows or []}
