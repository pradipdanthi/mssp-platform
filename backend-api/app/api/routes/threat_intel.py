"""
Threat Intelligence & Enrichment — customer + admin APIs.

Customer payloads use capability labels only (no MISP/OTX/AbuseIPDB brand names).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_current_user, require_roles, require_tenant_match
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_all, fetch_one
from app.services import threat_intel_service as ti

router = APIRouter(tags=["threat-intelligence"])


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


@router.get("/customer/threat-intel/{short_code}/summary")
def customer_threat_intel_summary(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    summary = ti.get_summary(tenant["id"])
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **summary,
    }


@router.get("/customer/threat-intel/{short_code}/iocs")
def customer_threat_intel_iocs(
    short_code: str,
    ioc_type: Optional[str] = Query(default=None, max_length=16),
    reputation_status: Optional[str] = Query(default=None, max_length=16),
    mitre_tactic: Optional[str] = Query(default=None, max_length=64),
    min_confidence: Optional[int] = Query(default=None, ge=0, le=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    rows, total = ti.list_iocs(
        tenant["id"],
        ioc_type=ioc_type,
        reputation_status=reputation_status,
        mitre_tactic=mitre_tactic,
        min_confidence=min_confidence,
        page=page,
        page_size=page_size,
    )
    pages = max(1, (total + page_size - 1) // page_size) if total else 1
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "iocs": rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": pages,
        },
    }


@router.get("/customer/threat-intel/{short_code}/campaigns")
def customer_threat_intel_campaigns(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "campaigns": ti.list_campaigns(tenant["id"]),
    }


@router.post("/admin/threat-intel/{tenant_ref}/sync")
def admin_threat_intel_sync(
    tenant_ref: str,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = _resolve_tenant_ref(tenant_ref)
    result = ti.sync_tenant_threat_intel(tenant["id"])
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **result,
    }


@router.get("/admin/threat-intel/summary")
def admin_threat_intel_summary(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
            t.short_code,
            t.name AS tenant_name,
            COALESCE(i.ioc_count, 0) AS ioc_count,
            COALESCE(i.malicious_count, 0) AS malicious_count,
            COALESCE(c.campaign_count, 0) AS campaign_count,
            i.last_seen::text AS last_ioc_seen
        FROM tenants t
        LEFT JOIN LATERAL (
            SELECT
                count(*)::int AS ioc_count,
                count(*) FILTER (WHERE reputation_status = 'MALICIOUS')::int AS malicious_count,
                max(last_seen_in_tenant) AS last_seen
            FROM tenant_threat_intel_iocs ti
            WHERE ti.tenant_id = t.id AND ti.status = 'active'
        ) i ON TRUE
        LEFT JOIN LATERAL (
            SELECT count(*)::int AS campaign_count
            FROM tenant_threat_intel_campaigns tc
            WHERE tc.tenant_id = t.id AND tc.status = 'active'
        ) c ON TRUE
        WHERE t.status = 'active'
        ORDER BY t.name ASC;
        """
    )
    return {"tenants": rows or []}
