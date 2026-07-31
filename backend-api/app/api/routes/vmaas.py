"""
Vulnerability Management (VMaaS) — customer + admin APIs.

Customer payloads use MSSP Internal Vulnerability Scanner labeling only.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user, require_roles, require_tenant_match
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_all, fetch_one
from app.services import vmaas_service as vmaas

router = APIRouter(tags=["vmaas-vulnerability-management"])

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
            "SELECT id::text, name, short_code, status FROM tenants WHERE id = %s::uuid;",
            (tenant_ref,),
        )
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant
    return _resolve_tenant(tenant_ref)


class ScanRequestBody(BaseModel):
    target_range: Optional[str] = Field(default=None, max_length=500)
    scan_engine: str = Field(default="NUCLEI_INTERNAL", max_length=32)


@router.get("/customer/vmaas/{short_code}/summary")
def customer_vmaas_summary(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    summary = vmaas.get_summary(tenant["id"])
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **summary,
    }


@router.get("/customer/vmaas/{short_code}/findings")
def customer_vmaas_findings(
    short_code: str,
    severity: Optional[str] = Query(default=None, max_length=16),
    status: Optional[str] = Query(default="OPEN", max_length=32),
    cve_id: Optional[str] = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    rows, total = vmaas.list_findings(
        tenant["id"],
        severity=severity,
        status=status,
        cve_id=cve_id,
        page=page,
        page_size=page_size,
    )
    pages = max(1, (total + page_size - 1) // page_size) if total else 1
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "findings": rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": pages,
        },
    }


@router.get("/customer/vmaas/{short_code}/scans")
def customer_vmaas_scans(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    # Customer-safe: omit scan_engine vendor codes — map to generic label.
    scans = []
    for row in vmaas.list_scans(tenant["id"]):
        scans.append(
            {
                "id": row["id"],
                "target_range": row.get("target_range"),
                "status": row.get("status"),
                "critical_count": row.get("critical_count"),
                "high_count": row.get("high_count"),
                "medium_count": row.get("medium_count"),
                "low_count": row.get("low_count"),
                "findings_count": row.get("findings_count"),
                "risk_score": row.get("risk_score"),
                "executed_at": row.get("executed_at"),
                "completed_at": row.get("completed_at"),
                "scanner_label": vmaas.ENGINE_LABEL,
            }
        )
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "scans": scans,
    }


@router.post("/customer/vmaas/{short_code}/scan", status_code=201)
def customer_vmaas_scan(
    short_code: str,
    body: Optional[ScanRequestBody] = None,
    current_user: Dict[str, Any] = Depends(require_roles(*CUSTOMER_ADMIN, *ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    body = body or ScanRequestBody()
    # Force generic engine path for customers (never echo vendor choice).
    result = vmaas.run_tenant_vmaas_sync(
        tenant["id"],
        target_range=body.target_range,
        scan_engine="NUCLEI_INTERNAL",
    )
    if result.get("scan_status") == "FAILED":
        raise HTTPException(status_code=422, detail=result.get("message") or "Scan failed")
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **result,
    }


@router.post("/admin/vmaas/{tenant_ref}/sync")
def admin_vmaas_sync(
    tenant_ref: str,
    body: Optional[ScanRequestBody] = None,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = _resolve_tenant_ref(tenant_ref)
    body = body or ScanRequestBody()
    engine = (body.scan_engine or "NUCLEI_INTERNAL").upper()
    result = vmaas.run_tenant_vmaas_sync(
        tenant["id"],
        target_range=body.target_range,
        scan_engine=engine,
    )
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **result,
    }


@router.get("/admin/vmaas/summary")
def admin_vmaas_summary(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
            t.short_code,
            t.name AS tenant_name,
            COALESCE(f.open_findings, 0) AS open_findings,
            COALESCE(f.critical_count, 0) AS critical_count,
            COALESCE(f.high_count, 0) AS high_count,
            s.status AS last_scan_status,
            s.completed_at::text AS last_scan_at
        FROM tenants t
        LEFT JOIN LATERAL (
            SELECT
                count(*) FILTER (WHERE status = 'OPEN')::int AS open_findings,
                count(*) FILTER (WHERE status = 'OPEN' AND severity = 'CRITICAL')::int AS critical_count,
                count(*) FILTER (WHERE status = 'OPEN' AND severity = 'HIGH')::int AS high_count
            FROM tenant_vulnerability_findings vf
            WHERE vf.tenant_id = t.id
        ) f ON TRUE
        LEFT JOIN LATERAL (
            SELECT status, completed_at
            FROM tenant_vulnerability_scans vs
            WHERE vs.tenant_id = t.id
            ORDER BY created_at DESC
            LIMIT 1
        ) s ON TRUE
        WHERE t.status = 'active'
        ORDER BY t.name ASC;
        """
    )
    return {"tenants": rows or []}
