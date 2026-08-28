"""Admin SOC alert suppressions CRUD (/v1/suppressions)."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import require_roles
from app.db.session import fetch_all, fetch_one, fetch_one_write
from app.schemas.suppressions import SuppressionCreateRequest, SuppressionPatchRequest
from app.services.audit_service import audit_from_user
from app.services.list_pagination import clamp_pagination, pagination_meta

router = APIRouter(prefix="/v1/suppressions", tags=["suppressions"])

ADMIN_SOC_ROLES = ("platform_admin", "soc_manager", "soc_analyst")
GLOBAL_SUPPRESSION_ROLES = ("platform_admin", "soc_manager")

_SELECT_COLS = """
    s.id::text,
    s.tenant_id::text,
    t.name AS tenant_name,
    t.short_code AS tenant_short_code,
    s.hostname,
    s.rule_id,
    s.scope,
    s.match_process_path,
    s.process_path_value,
    s.match_parent_process,
    s.parent_process_value,
    s.match_file_hash,
    s.file_hash_value,
    s.match_hostname,
    s.hostname_value,
    s.expires_at,
    s.reason,
    s.created_by_user_id::text,
    creator.full_name AS created_by,
    s.created_at,
    s.disabled_at
"""


def _row_or_404(suppression_id: UUID) -> Dict[str, Any]:
    row = fetch_one(
        f"""
        SELECT {_SELECT_COLS}
        FROM alert_suppressions s
        LEFT JOIN tenants t ON t.id = s.tenant_id
        LEFT JOIN platform_users creator ON creator.id = s.created_by_user_id
        WHERE s.id = %s;
        """,
        (suppression_id,),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suppression not found")
    return row


@router.get("")
def list_suppressions(
    tenant_id: Optional[UUID] = None,
    rule_id: Optional[str] = Query(default=None, max_length=128),
    scope: Optional[str] = Query(default=None, max_length=16),
    include_disabled: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    page, page_size, offset = clamp_pagination(page, page_size)
    where = []
    params: list = []
    if not include_disabled:
        where.append("s.disabled_at IS NULL")
    if tenant_id is not None:
        # Include tenant-scoped + host-scoped for that tenant, plus globals.
        where.append("(s.tenant_id = %s OR s.scope = 'global')")
        params.append(tenant_id)
    if rule_id:
        where.append("s.rule_id = %s")
        params.append(rule_id.strip())
    if scope in ("global", "tenant", "host"):
        where.append("s.scope = %s")
        params.append(scope)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    count_row = fetch_one(
        f"""
        SELECT count(*)::int AS total
        FROM alert_suppressions s
        {where_sql};
        """,
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)
    rows = fetch_all(
        f"""
        SELECT {_SELECT_COLS}
        FROM alert_suppressions s
        LEFT JOIN tenants t ON t.id = s.tenant_id
        LEFT JOIN platform_users creator ON creator.id = s.created_by_user_id
        {where_sql}
        ORDER BY s.created_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return {"suppressions": rows, **pagination_meta(total, page, page_size)}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_suppression(
    payload: SuppressionCreateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    role = current_user.get("role")
    if payload.scope == "global" and role not in GLOBAL_SUPPRESSION_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform_admin or soc_manager can create global suppressions",
        )

    if payload.tenant_id is not None:
        tenant = fetch_one(
            "SELECT id::text FROM tenants WHERE id = %s;",
            (payload.tenant_id,),
        )
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    hostname_value = payload.hostname_value
    if payload.match_hostname and not hostname_value and payload.hostname:
        hostname_value = payload.hostname

    row = fetch_one_write(
        """
        INSERT INTO alert_suppressions (
            tenant_id, hostname, rule_id, scope,
            match_process_path, process_path_value,
            match_parent_process, parent_process_value,
            match_file_hash, file_hash_value,
            match_hostname, hostname_value,
            expires_at, reason, created_by_user_id
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s
        )
        RETURNING id::text;
        """,
        (
            str(payload.tenant_id) if payload.tenant_id else None,
            payload.hostname,
            payload.rule_id,
            payload.scope,
            payload.match_process_path,
            payload.process_path_value,
            payload.match_parent_process,
            payload.parent_process_value,
            payload.match_file_hash,
            payload.file_hash_value,
            payload.match_hostname,
            hostname_value,
            payload.expires_at,
            payload.reason,
            current_user["id"],
        ),
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create suppression",
        )
    created = _row_or_404(UUID(row["id"]))
    audit_from_user(
        current_user,
        action="suppression.create",
        entity_type="alert_suppression",
        entity_id=created["id"],
        tenant_id=created.get("tenant_id"),
        details={
            "scope": created.get("scope"),
            "rule_id": created.get("rule_id"),
            "hostname": created.get("hostname"),
        },
    )
    return {"suppression": created}


@router.patch("/{suppression_id}")
def patch_suppression(
    suppression_id: UUID,
    payload: SuppressionPatchRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    existing = _row_or_404(suppression_id)
    if existing.get("scope") == "global" and current_user.get("role") not in GLOBAL_SUPPRESSION_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform_admin or soc_manager can modify global suppressions",
        )

    assignments = []
    values: list = []
    if "expires_at" in payload.model_fields_set:
        assignments.append("expires_at = %s")
        values.append(payload.expires_at)
    if "reason" in payload.model_fields_set:
        assignments.append("reason = %s")
        values.append(payload.reason)
    if "disabled" in payload.model_fields_set:
        if payload.disabled:
            assignments.append("disabled_at = COALESCE(disabled_at, now())")
        else:
            assignments.append("disabled_at = NULL")

    if not assignments:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No updatable fields provided",
        )

    values.append(suppression_id)
    updated = fetch_one_write(
        f"""
        UPDATE alert_suppressions
        SET {", ".join(assignments)}
        WHERE id = %s
        RETURNING id::text;
        """,
        tuple(values),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suppression not found")

    result = _row_or_404(suppression_id)
    audit_from_user(
        current_user,
        action="suppression.update",
        entity_type="alert_suppression",
        entity_id=result["id"],
        tenant_id=result.get("tenant_id"),
        details={"fields": sorted(payload.model_fields_set)},
    )
    return {"suppression": result}


@router.delete("/{suppression_id}")
def delete_suppression(
    suppression_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Soft-disable a suppression (sets disabled_at)."""
    existing = _row_or_404(suppression_id)
    if existing.get("scope") == "global" and current_user.get("role") not in GLOBAL_SUPPRESSION_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform_admin or soc_manager can disable global suppressions",
        )

    updated = fetch_one_write(
        """
        UPDATE alert_suppressions
        SET disabled_at = COALESCE(disabled_at, now())
        WHERE id = %s
        RETURNING id::text;
        """,
        (suppression_id,),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suppression not found")

    result = _row_or_404(suppression_id)
    audit_from_user(
        current_user,
        action="suppression.disable",
        entity_type="alert_suppression",
        entity_id=result["id"],
        tenant_id=result.get("tenant_id"),
        details={"scope": result.get("scope"), "rule_id": result.get("rule_id")},
    )
    return {"suppression": result}
