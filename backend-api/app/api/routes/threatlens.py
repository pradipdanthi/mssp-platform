"""Kevantic ThreatLens + Retrospective Engine APIs (customer + admin)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import get_current_user, require_roles, require_tenant_match
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_one
from app.services import retrospective_service as retro
from app.services import threat_intel_service as ti
from app.services import threatlens_nlp

router = APIRouter(tags=["threatlens-retrospective"])


def _tenant_threatlens_allowed(tenant_id: str) -> bool:
    """ThreatLens spans Card 7 (TI / retro) and Card 8 (forensics / IOC extract)."""
    row = fetch_one(
        """
        SELECT
            COALESCE(misp_enabled, FALSE) AS ti,
            COALESCE(velociraptor_enabled, FALSE) AS forensics
        FROM tenant_entitlements
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    )
    if not row:
        return False
    return bool(row.get("ti") or row.get("forensics"))


def _require_threatlens(tenant_id: str) -> None:
    if not _tenant_threatlens_allowed(tenant_id):
        raise HTTPException(
            status_code=403,
            detail=(
                "Kevantic ThreatLens requires Threat Intelligence and/or "
                "Endpoint Forensics entitlement. Request enablement from your MSSP."
            ),
        )



class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", max_length=500_000)
    url: Optional[str] = Field(default=None, max_length=2048)


class SweepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", max_length=500_000)
    url: Optional[str] = Field(default=None, max_length=2048)
    iocs: Optional[List[Any]] = None
    lookback_days: int = Field(default=90, ge=1, le=400)


class StixIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle: Dict[str, Any]


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


def _tenant_from_user(current_user: Dict[str, Any]) -> Dict[str, Any]:
    tid = current_user.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant = fetch_one(
        "SELECT id::text, name, short_code, status FROM tenants WHERE id = %s::uuid;",
        (tid,),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


# ---------- Customer (short_code paths — existing portal convention) ----------


@router.post("/customer/threatlens/{short_code}/extract")
def customer_threatlens_extract(
    short_code: str,
    body: ExtractRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    _require_threatlens(tenant["id"])
    if not (body.text or "").strip() and not body.url:
        raise HTTPException(status_code=400, detail="Provide text or url")
    result = threatlens_nlp.extract_iocs(body.text or "", url=body.url)
    return {"tenant": {"short_code": tenant["short_code"], "name": tenant["name"]}, **result}


@router.post(
    "/customer/threatlens/{short_code}/sweep",
    status_code=status.HTTP_202_ACCEPTED,
)
def customer_threatlens_sweep(
    short_code: str,
    body: SweepRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    _require_threatlens(tenant["id"])
    iocs = body.iocs
    if not iocs:
        extracted = threatlens_nlp.extract_iocs(body.text or "", url=body.url)
        iocs = extracted.get("ioc_values") or []
    try:
        job = retro.create_hunt_job(
            tenant["id"],
            iocs,
            lookback_days=body.lookback_days,
            created_by=current_user.get("id"),
            source="threatlens",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(retro.enqueue_job_execution, job["id"])
    return {
        "accepted": True,
        "job_id": job["id"],
        "execution_mode": job["execution_mode"],
        "status": job["status"],
        "engine": retro.ENGINE_LABEL,
        "message": "90-day retrospective hunt queued",
    }


@router.get("/customer/threatlens/{short_code}/jobs/{job_id}")
def customer_threatlens_job(
    short_code: str,
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    _require_threatlens(tenant["id"])
    job = retro.get_job(job_id, tenant_id=tenant["id"])
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"tenant": {"short_code": tenant["short_code"]}, "job": job}


@router.get("/customer/threatlens/{short_code}/jobs")
def customer_threatlens_jobs(
    short_code: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    _require_threatlens(tenant["id"])
    rows, total = retro.list_jobs(tenant_id=tenant["id"], page=page, page_size=page_size)
    return {
        "tenant": {"short_code": tenant["short_code"]},
        "jobs": rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": max(1, (total + page_size - 1) // page_size) if total else 1,
        },
    }


# ---------- Prompt-style /api/v1 aliases (tenant from JWT) ----------


@router.post("/api/v1/customer/threatlens/extract")
def v1_threatlens_extract(
    body: ExtractRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _tenant_from_user(current_user)
    require_tenant_match(tenant["id"], current_user)
    _require_threatlens(tenant["id"])
    if not (body.text or "").strip() and not body.url:
        raise HTTPException(status_code=400, detail="Provide text or url")
    result = threatlens_nlp.extract_iocs(body.text or "", url=body.url)
    return {"tenant": {"short_code": tenant["short_code"], "name": tenant["name"]}, **result}


@router.post("/api/v1/customer/threatlens/sweep", status_code=status.HTTP_202_ACCEPTED)
def v1_threatlens_sweep(
    body: SweepRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _tenant_from_user(current_user)
    require_tenant_match(tenant["id"], current_user)
    _require_threatlens(tenant["id"])
    iocs = body.iocs
    if not iocs:
        extracted = threatlens_nlp.extract_iocs(body.text or "", url=body.url)
        iocs = extracted.get("ioc_values") or []
    try:
        job = retro.create_hunt_job(
            tenant["id"],
            iocs,
            lookback_days=body.lookback_days,
            created_by=current_user.get("id"),
            source="threatlens",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(retro.enqueue_job_execution, job["id"])
    return {
        "accepted": True,
        "job_id": job["id"],
        "execution_mode": job["execution_mode"],
        "status": job["status"],
        "engine": retro.ENGINE_LABEL,
    }


# ---------- Admin ----------


@router.get("/admin/retrospective-hunts")
def admin_retrospective_hunts(
    status_filter: Optional[str] = Query(default=None, alias="status", max_length=16),
    tenant_id: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    rows, total = retro.list_jobs(
        tenant_id=tenant_id, status=status_filter, page=page, page_size=page_size
    )
    return {
        "engine": retro.ENGINE_LABEL,
        "jobs": rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": max(1, (total + page_size - 1) // page_size) if total else 1,
        },
    }


@router.get("/admin/appliances/command-summary")
def admin_appliance_command_summary(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    return retro.appliance_command_summary()


@router.post("/admin/threat-intel/{tenant_ref}/stix-ingest")
def admin_stix_ingest(
    tenant_ref: str,
    body: StixIngestRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    if len(tenant_ref) == 36 and tenant_ref.count("-") == 4:
        tenant = fetch_one(
            "SELECT id::text, name, short_code FROM tenants WHERE id = %s::uuid;",
            (tenant_ref,),
        )
    else:
        tenant = _resolve_tenant(tenant_ref)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    result = ti.ingest_stix_bundle_for_tenant(tenant["id"], body.bundle)
    return {"tenant": {"short_code": tenant["short_code"], "name": tenant["name"]}, **result}
