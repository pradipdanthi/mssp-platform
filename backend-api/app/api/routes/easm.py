"""
External Attack Surface Management (EASM) — customer + admin APIs.

Customer payloads use capability labels only (MSSP External Surface Scanner).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user, require_roles, require_tenant_match
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_all, fetch_one
from app.services import easm_service as easm

router = APIRouter(tags=["easm-attack-surface"])

CUSTOMER_ADMIN = ("customer_admin",)
CUSTOMER_ROLES = ("customer_admin", "customer_viewer")


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


def _resolve_tenant_by_id(tenant_id: str) -> Dict[str, Any]:
    tenant = fetch_one(
        """
        SELECT id::text, name, short_code, status
        FROM tenants
        WHERE id = %s::uuid;
        """,
        (tenant_id,),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


class RegisterDomainBody(BaseModel):
    domain_or_ip: str = Field(min_length=1, max_length=253)
    notes: Optional[str] = Field(default=None, max_length=2000)
    start_scan: bool = True


class AdminScanBody(BaseModel):
    target_domain: Optional[str] = Field(default=None, max_length=253)
    async_mode: bool = False


@router.get("/customer/easm/{short_code}/summary")
def customer_easm_summary(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    summary = easm.get_summary(tenant["id"])
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **summary,
    }


@router.get("/customer/easm/{short_code}/assets")
def customer_easm_assets(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    assets = easm.list_assets(tenant["id"])
    # Customer-safe discovery labels
    safe: List[Dict[str, Any]] = []
    for row in assets:
        src = row.get("discovery_source") or ""
        if src in ("mssp_external_surface_scanner", "scanner", "nuclei", "amass"):
            label = easm.CUSTOMER_SCANNER_LABEL
        elif src == "customer_registration":
            label = "Customer registration"
        else:
            label = "Managed discovery"
        safe.append(
            {
                "id": row["id"],
                "domain_or_ip": row["domain_or_ip"],
                "asset_type": row["asset_type"],
                "discovery_source_label": label,
                "first_seen": row.get("first_seen"),
                "last_seen": row.get("last_seen"),
                "status": row.get("status"),
            }
        )
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "assets": safe,
    }


@router.get("/customer/easm/{short_code}/findings")
def customer_easm_findings(
    short_code: str,
    severity: Optional[str] = Query(default=None, max_length=16),
    finding_type: Optional[str] = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    rows, total = easm.list_findings(
        tenant["id"],
        severity=severity,
        finding_type=finding_type,
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


@router.post("/customer/easm/{short_code}/domains", status_code=201)
def customer_register_domain(
    short_code: str,
    body: RegisterDomainBody,
    current_user: Dict[str, Any] = Depends(require_roles(*CUSTOMER_ADMIN, *ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    try:
        asset = easm.register_primary_target(
            tenant["id"], body.domain_or_ip, notes=body.notes
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scan_result = None
    if body.start_scan:
        # Synchronous lightweight scan so UI can refresh immediately
        scan_result = easm.run_tenant_scan(
            tenant["id"], target_domain=asset.get("domain_or_ip")
        )

    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "asset": {
            "id": asset.get("id"),
            "domain_or_ip": asset.get("domain_or_ip"),
            "asset_type": asset.get("asset_type"),
            "status": asset.get("status"),
        },
        "scan": scan_result,
    }


# Prompt-compatible aliases (same handlers via path variants under /customer/easm)
@router.get("/customer/easm/{short_code}/findings/list")
def customer_easm_findings_alias(
    short_code: str,
    severity: Optional[str] = Query(default=None, max_length=16),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return customer_easm_findings(
        short_code, severity, None, page, page_size, current_user
    )


@router.post("/admin/easm/{tenant_ref}/scan")
def admin_easm_scan(
    tenant_ref: str,
    body: Optional[AdminScanBody] = None,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """
    Admin-triggered perimeter scan.
    ``tenant_ref`` may be tenant UUID or short_code.
    """
    body = body or AdminScanBody()
    if len(tenant_ref) == 36 and tenant_ref.count("-") == 4:
        tenant = _resolve_tenant_by_id(tenant_ref)
    else:
        tenant = _resolve_tenant(tenant_ref)

    if body.async_mode:
        easm.start_scan_async(tenant["id"], target_domain=body.target_domain)
        return {
            "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
            "scan_status": "PENDING",
            "message": "Perimeter scan queued",
        }

    result = easm.run_tenant_scan(tenant["id"], target_domain=body.target_domain)
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        **result,
    }


@router.get("/admin/easm/summary")
def admin_easm_summary(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
            t.short_code,
            t.name AS tenant_name,
            COALESCE(a.asset_count, 0) AS asset_count,
            COALESCE(f.open_findings, 0) AS open_findings,
            s.scan_status AS last_scan_status,
            s.completed_at::text AS last_scan_at
        FROM tenants t
        LEFT JOIN LATERAL (
            SELECT count(*)::int AS asset_count
            FROM tenant_easm_assets ea
            WHERE ea.tenant_id = t.id AND ea.status = 'ACTIVE'
        ) a ON TRUE
        LEFT JOIN LATERAL (
            SELECT count(*)::int AS open_findings
            FROM tenant_easm_findings ef
            WHERE ef.tenant_id = t.id AND ef.status = 'open'
        ) f ON TRUE
        LEFT JOIN LATERAL (
            SELECT scan_status, completed_at
            FROM tenant_easm_scans es
            WHERE es.tenant_id = t.id
            ORDER BY created_at DESC
            LIMIT 1
        ) s ON TRUE
        WHERE t.status = 'active'
        ORDER BY t.name ASC;
        """
    )
    return {"tenants": rows or []}
