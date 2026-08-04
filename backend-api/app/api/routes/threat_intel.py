"""
Threat Intelligence & Enrichment — customer + admin APIs.

Customer payloads use capability labels only (no MISP/OTX/AbuseIPDB brand names).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import get_current_user, require_roles, require_tenant_match
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_all, fetch_one
from app.services import threat_intel_service as ti

router = APIRouter(tags=["threat-intelligence"])


class TaxiiPullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_root: Optional[str] = Field(default=None, max_length=2048)
    collection_id: Optional[str] = Field(default=None, max_length=256)
    username: Optional[str] = Field(default=None, max_length=256)
    password: Optional[str] = Field(default=None, max_length=512)
    use_configured_feed: bool = False


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


# Static admin path MUST be registered before /{tenant_ref} routes.
@router.get("/admin/threat-intel/summary")
def admin_threat_intel_summary(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    rows = fetch_all(
        """
        SELECT
            t.id::text AS tenant_id,
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


@router.get("/admin/threat-intel/{tenant_ref}/detail")
def admin_threat_intel_tenant_detail(
    tenant_ref: str,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    tenant = _resolve_tenant_ref(tenant_ref)
    summary = ti.get_summary(tenant["id"])
    return {
        "tenant": {"id": tenant["id"], "short_code": tenant["short_code"], "name": tenant["name"]},
        **summary,
    }


@router.get("/admin/threat-intel/{tenant_ref}/iocs")
def admin_threat_intel_iocs(
    tenant_ref: str,
    ioc_type: Optional[str] = Query(default=None, max_length=16),
    reputation_status: Optional[str] = Query(default=None, max_length=16),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    tenant = _resolve_tenant_ref(tenant_ref)
    rows, total = ti.list_iocs(
        tenant["id"],
        ioc_type=ioc_type,
        reputation_status=reputation_status,
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


@router.get("/admin/threat-intel/{tenant_ref}/campaigns")
def admin_threat_intel_campaigns(
    tenant_ref: str,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    tenant = _resolve_tenant_ref(tenant_ref)
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "campaigns": ti.list_campaigns(tenant["id"]),
    }


@router.post("/admin/threat-intel/{tenant_ref}/taxii-pull")
def admin_threat_intel_taxii_pull(
    tenant_ref: str,
    body: TaxiiPullRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """
    Pull a STIX bundle from a TAXII 2.x collection and ingest into the tenant.
    Optional env defaults: JUNEXIS_TAXII_API_ROOT, JUNEXIS_TAXII_COLLECTION_ID,
    JUNEXIS_TAXII_USERNAME, JUNEXIS_TAXII_PASSWORD (never logged).
    """
    _ = current_user
    tenant = _resolve_tenant_ref(tenant_ref)

    api_root = (body.api_root or "").strip()
    collection_id = (body.collection_id or "").strip()
    username = body.username
    password = body.password

    if body.use_configured_feed or not api_root or not collection_id:
        api_root = api_root or os.getenv("JUNEXIS_TAXII_API_ROOT", "").strip()
        collection_id = collection_id or os.getenv("JUNEXIS_TAXII_COLLECTION_ID", "").strip()
        if username is None:
            username = os.getenv("JUNEXIS_TAXII_USERNAME") or None
        if password is None:
            password = os.getenv("JUNEXIS_TAXII_PASSWORD") or None

    if not api_root or not collection_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "TAXII api_root and collection_id are required "
                "(or set JUNEXIS_TAXII_API_ROOT / JUNEXIS_TAXII_COLLECTION_ID)."
            ),
        )

    try:
        bundle = ti.pull_taxii_collection(
            api_root,
            collection_id,
            username=username,
            password=password,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"TAXII pull failed: {type(exc).__name__}",
        ) from exc

    result = ti.ingest_stix_bundle_for_tenant(tenant["id"], bundle)
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "taxii": {
            "api_root": api_root,
            "collection_id": collection_id,
            "objects_pulled": len((bundle or {}).get("objects") or []),
        },
        **result,
    }
