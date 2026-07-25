"""
KB-066/067: Admin ops catalog — monthly reports, protected assets, audit logs.

Write roles: platform_admin + soc_manager.
Read roles: ADMIN_SOC_ROLES.
KB-067: projected `sections` only (never raw metrics JSONB / report_file_path).
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from psycopg.errors import UniqueViolation

from app.api.dependencies import require_roles
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_all, fetch_one, fetch_one_write
from app.schemas.admin_ops import (
    AssetCreateRequest,
    AssetDetail,
    AssetUpdateRequest,
    ReportCreateRequest,
    ReportDetail,
    ReportUpdateRequest,
)
from app.schemas.report_snapshot import EMPTY_NARRATIVE
from app.services.report_export_service import build_pdf_bytes, build_xlsx_bytes, export_filename
from app.services.report_snapshot_service import (
    ensure_snapshot_for_publish,
    get_safe_sections_for_report,
    refresh_and_store,
)

router = APIRouter(prefix="/admin", tags=["admin-ops"])
WRITE_ROLES = ("platform_admin", "soc_manager")


def _narrative_from_payload(payload: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key in EMPTY_NARRATIVE:
        if key in getattr(payload, "model_fields_set", set()):
            value = getattr(payload, key)
            out[key] = "" if value is None else str(value)
    return out


def _report_detail(report_id: UUID, include_sections: bool = True) -> Optional[Dict[str, Any]]:
    row = fetch_one(
        """
        SELECT
            mr.id::text,
            mr.tenant_id::text,
            t.name AS tenant_name,
            t.short_code,
            mr.report_month::text,
            ('Monthly Security Report — ' || to_char(mr.report_month, 'Mon YYYY')) AS title,
            mr.status,
            mr.executive_summary,
            mr.published_at::text,
            mr.created_at::text,
            mr.updated_at::text
        FROM monthly_reports mr
        JOIN tenants t ON t.id = mr.tenant_id
        WHERE mr.id = %s;
        """,
        (str(report_id),),
    )
    if not row:
        return None
    if include_sections:
        row["sections"] = get_safe_sections_for_report(report_id)
    return row


def _asset_detail(asset_id: UUID) -> Optional[Dict[str, Any]]:
    return fetch_one(
        """
        SELECT
            pa.id::text,
            pa.tenant_id::text,
            t.name AS tenant_name,
            t.short_code,
            pa.appliance_id::text,
            a.appliance_name,
            pa.hostname,
            host(pa.ip_address) AS ip_address,
            pa.asset_type,
            pa.os_name,
            pa.criticality,
            pa.owner,
            pa.status,
            pa.last_seen_at::text,
            pa.created_at::text,
            pa.updated_at::text
        FROM protected_assets pa
        JOIN tenants t ON t.id = pa.tenant_id
        LEFT JOIN appliances a ON a.id = pa.appliance_id
        WHERE pa.id = %s;
        """,
        (str(asset_id),),
    )


@router.get("/reports")
def list_reports(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, List[Dict[str, Any]]]:
    rows = fetch_all(
        """
        SELECT
            mr.id::text,
            mr.tenant_id::text,
            t.name AS tenant_name,
            t.short_code,
            mr.report_month::text,
            ('Monthly Security Report — ' || to_char(mr.report_month, 'Mon YYYY')) AS title,
            mr.status,
            left(coalesce(mr.executive_summary, ''), 240) AS summary_preview,
            mr.published_at::text,
            mr.created_at::text
        FROM monthly_reports mr
        JOIN tenants t ON t.id = mr.tenant_id
        ORDER BY mr.report_month DESC, mr.created_at DESC
        LIMIT 100;
        """
    )
    return {"reports": rows}


@router.get("/reports/{report_id}", response_model=ReportDetail)
def get_report(
    report_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    row = _report_detail(report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return row


@router.post("/reports", response_model=ReportDetail, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ReportCreateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*WRITE_ROLES)),
) -> Dict[str, Any]:
    tenant = fetch_one("SELECT id FROM tenants WHERE id = %s;", (str(payload.tenant_id),))
    if not tenant:
        raise HTTPException(status_code=422, detail="tenant_id does not reference an existing tenant")

    published_at_sql = "now()" if payload.status == "published" else "NULL"
    try:
        created = fetch_one_write(
            f"""
            INSERT INTO monthly_reports (tenant_id, report_month, status, executive_summary, published_at, metrics)
            VALUES (%s, %s, %s, %s, {published_at_sql}, '{{}}'::jsonb)
            RETURNING id::text;
            """,
            (
                str(payload.tenant_id),
                payload.report_month.isoformat(),
                payload.status,
                payload.executive_summary,
            ),
        )
    except UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="A report for this tenant and month already exists",
        )

    report_id = UUID(created["id"])
    narrative = _narrative_from_payload(payload)
    refresh_and_store(report_id, narrative_override=narrative or None)
    if payload.status == "published":
        ensure_snapshot_for_publish(report_id)

    row = _report_detail(report_id)
    if not row:
        raise HTTPException(status_code=500, detail="Report creation failed")
    return row


@router.patch("/reports/{report_id}", response_model=ReportDetail)
def update_report(
    report_id: UUID,
    payload: ReportUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*WRITE_ROLES)),
) -> Dict[str, Any]:
    if not _report_detail(report_id, include_sections=False):
        raise HTTPException(status_code=404, detail="Report not found")

    fields = []
    params: list = []
    if "executive_summary" in payload.model_fields_set:
        fields.append("executive_summary = %s")
        params.append(payload.executive_summary)
    if "status" in payload.model_fields_set and payload.status is not None:
        fields.append("status = %s")
        params.append(payload.status)
        if payload.status == "published":
            fields.append("published_at = coalesce(published_at, now())")
        elif payload.status == "draft":
            fields.append("published_at = NULL")

    narrative = _narrative_from_payload(payload)
    if narrative:
        refresh_and_store(report_id, narrative_override=narrative)

    if fields:
        params.append(str(report_id))
        updated = fetch_one_write(
            f"UPDATE monthly_reports SET {', '.join(fields)} WHERE id = %s RETURNING id::text;",
            tuple(params),
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Report not found")

    if "status" in payload.model_fields_set and payload.status == "published":
        ensure_snapshot_for_publish(report_id)

    if not fields and not narrative:
        raise HTTPException(status_code=422, detail="At least one field must be provided")

    row = _report_detail(report_id)
    if not row:
        raise HTTPException(status_code=500, detail="Report update failed")
    return row


@router.post("/reports/{report_id}/refresh-metrics", response_model=ReportDetail)
def refresh_report_metrics(
    report_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*WRITE_ROLES)),
) -> Dict[str, Any]:
    try:
        refresh_and_store(report_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Report not found")
    row = _report_detail(report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return row


def _admin_download(report_id: UUID, fmt: str) -> Response:
    row = _report_detail(report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    sections = row.get("sections") or {}
    if fmt == "pdf":
        content = build_pdf_bytes(
            title=row["title"],
            executive_summary=row.get("executive_summary"),
            published_at=row.get("published_at"),
            sections=sections,
        )
        media = "application/pdf"
        filename = export_filename(row["short_code"], row["report_month"], "pdf")
    else:
        content = build_xlsx_bytes(
            title=row["title"],
            executive_summary=row.get("executive_summary"),
            published_at=row.get("published_at"),
            sections=sections,
        )
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = export_filename(row["short_code"], row["report_month"], "xlsx")
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/{report_id}/download.pdf")
def download_report_pdf(
    report_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Response:
    return _admin_download(report_id, "pdf")


@router.get("/reports/{report_id}/download.xlsx")
def download_report_xlsx(
    report_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Response:
    return _admin_download(report_id, "xlsx")


@router.get("/assets")
def list_assets(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, List[Dict[str, Any]]]:
    rows = fetch_all(
        """
        SELECT
            pa.id::text,
            t.name AS tenant_name,
            t.short_code,
            pa.hostname,
            host(pa.ip_address) AS ip_address,
            pa.asset_type,
            pa.criticality,
            pa.status,
            a.appliance_name,
            pa.last_seen_at::text,
            pa.created_at::text
        FROM protected_assets pa
        JOIN tenants t ON t.id = pa.tenant_id
        LEFT JOIN appliances a ON a.id = pa.appliance_id
        ORDER BY pa.created_at DESC
        LIMIT 100;
        """
    )
    return {"assets": rows}


@router.get("/assets/{asset_id}", response_model=AssetDetail)
def get_asset(
    asset_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    row = _asset_detail(asset_id)
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")
    return row


@router.post("/assets", response_model=AssetDetail, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*WRITE_ROLES)),
) -> Dict[str, Any]:
    tenant = fetch_one("SELECT id FROM tenants WHERE id = %s;", (str(payload.tenant_id),))
    if not tenant:
        raise HTTPException(status_code=422, detail="tenant_id does not reference an existing tenant")

    if payload.appliance_id is not None:
        appliance = fetch_one(
            "SELECT id FROM appliances WHERE id = %s AND tenant_id = %s;",
            (str(payload.appliance_id), str(payload.tenant_id)),
        )
        if not appliance:
            raise HTTPException(
                status_code=422,
                detail="appliance_id not found for this tenant",
            )

    created = fetch_one_write(
        """
        INSERT INTO protected_assets (
            tenant_id, appliance_id, hostname, asset_type, os_name, criticality, owner, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id::text;
        """,
        (
            str(payload.tenant_id),
            str(payload.appliance_id) if payload.appliance_id else None,
            payload.hostname,
            payload.asset_type,
            payload.os_name,
            payload.criticality,
            payload.owner,
            payload.status,
        ),
    )
    row = _asset_detail(UUID(created["id"]))
    if not row:
        raise HTTPException(status_code=500, detail="Asset creation failed")
    return row


@router.patch("/assets/{asset_id}", response_model=AssetDetail)
def update_asset(
    asset_id: UUID,
    payload: AssetUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*WRITE_ROLES)),
) -> Dict[str, Any]:
    existing = _asset_detail(asset_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Asset not found")

    fields = []
    params: list = []
    for field_name in ("hostname", "asset_type", "criticality", "status", "os_name", "owner"):
        if field_name in payload.model_fields_set:
            fields.append(f"{field_name} = %s")
            params.append(getattr(payload, field_name))
    if "appliance_id" in payload.model_fields_set:
        appliance_id = payload.appliance_id
        if appliance_id is not None:
            appliance = fetch_one(
                "SELECT id FROM appliances WHERE id = %s AND tenant_id = %s;",
                (str(appliance_id), existing["tenant_id"]),
            )
            if not appliance:
                raise HTTPException(status_code=422, detail="appliance_id not found for this tenant")
        fields.append("appliance_id = %s")
        params.append(str(appliance_id) if appliance_id else None)

    if not fields:
        raise HTTPException(status_code=422, detail="At least one field must be provided")

    params.append(str(asset_id))
    updated = fetch_one_write(
        f"UPDATE protected_assets SET {', '.join(fields)} WHERE id = %s RETURNING id::text;",
        tuple(params),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Asset not found")
    row = _asset_detail(UUID(updated["id"]))
    if not row:
        raise HTTPException(status_code=500, detail="Asset update failed")
    return row


@router.get("/audit-logs")
def list_audit_logs(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, List[Dict[str, Any]]]:
    rows = fetch_all(
        """
        SELECT
            al.id::text,
            t.name AS tenant_name,
            t.short_code,
            pu.email AS actor_email,
            al.action,
            al.entity_type,
            al.entity_id::text,
            host(al.source_ip) AS source_ip,
            al.created_at::text
        FROM audit_logs al
        LEFT JOIN tenants t ON t.id = al.tenant_id
        LEFT JOIN platform_users pu ON pu.id = al.actor_user_id
        ORDER BY al.created_at DESC
        LIMIT 100;
        """
    )
    return {"audit_logs": rows}
