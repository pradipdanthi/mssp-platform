"""
KB-013: Admin Tenant Management API Foundation.

New endpoints alongside (not replacing) the existing GET /admin/tenants
list endpoint in app/api/routes/admin.py, which this module does not
import from for logic and does not modify in any way:

- GET   /admin/tenants/{tenant_id}  - single tenant detail
- POST  /admin/tenants              - create a tenant
- PATCH /admin/tenants/{tenant_id}  - update basic tenant fields

RBAC (approved decision 1A):
- platform_admin, soc_manager, soc_analyst can all GET tenant detail
  (same read access as the existing GET /admin/tenants list).
- Only platform_admin can POST (create) or PATCH (update). soc_manager and
  soc_analyst are read-only for tenant management and get 403 on
  POST/PATCH, same as customer roles.

There is intentionally no DELETE endpoint - nearly every other table
(appliances, alerts, incidents, etc.) has ON DELETE CASCADE back to
tenants, so a real delete would destroy a tenant's entire history.
Deactivating a tenant is done via PATCH with {"status": "inactive"} or
{"status": "suspended"} instead (soft-delete style, using values the
tenants table's CHECK constraint already allows).

tenant_id is a UUID path parameter, validated by FastAPI/Pydantic before
it ever reaches a database query - an invalid UUID never produces a raw
database error, only a clean 422.
"""

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.errors import UniqueViolation

from app.api.dependencies import require_roles
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_one, fetch_one_write
from app.schemas.tenants import TenantCreateRequest, TenantDetail, TenantUpdateRequest

router = APIRouter(prefix="/admin/tenants", tags=["admin-tenants"])

# KB-013: only platform_admin may create or update tenant records.
# soc_manager and soc_analyst keep read-only access (ADMIN_SOC_ROLES,
# imported from admin.py) for tenant detail, same as the existing list.
ADMIN_TENANT_WRITE_ROLES = ("platform_admin",)


def _fetch_tenant_detail(tenant_id: UUID) -> Optional[Dict[str, Any]]:
    row = fetch_one(
        """
        SELECT
            t.id::text,
            t.name,
            t.short_code,
            t.status,
            t.sla_level,
            t.business_criticality,
            t.timezone,
            t.notes,
            t.created_at::text,
            t.updated_at::text,
            count(DISTINCT a.id) AS appliances,
            count(DISTINCT pa.id) AS protected_assets,
            count(DISTINCT i.id) AS incidents
        FROM tenants t
        LEFT JOIN appliances a ON a.tenant_id = t.id
        LEFT JOIN protected_assets pa ON pa.tenant_id = t.id
        LEFT JOIN incidents i ON i.tenant_id = t.id
        WHERE t.id = %s
        GROUP BY t.id;
        """,
        (str(tenant_id),),
    )
    return row or None


@router.get("/{tenant_id}", response_model=TenantDetail)
def get_tenant_detail(
    tenant_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = _fetch_tenant_detail(tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.post("", response_model=TenantDetail, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_TENANT_WRITE_ROLES)),
) -> Dict[str, Any]:
    existing = fetch_one(
        "SELECT id FROM tenants WHERE short_code = %s;",
        (payload.short_code,),
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A tenant with this short_code already exists",
        )

    try:
        created = fetch_one_write(
            """
            INSERT INTO tenants (name, short_code, status, sla_level, business_criticality, timezone, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id::text;
            """,
            (
                payload.name,
                payload.short_code,
                payload.status,
                payload.sla_level,
                payload.business_criticality,
                payload.timezone,
                payload.notes,
            ),
        )
    except UniqueViolation:
        # Race-condition backstop: two concurrent requests could both pass
        # the SELECT check above before either INSERT commits.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A tenant with this short_code already exists",
        )

    tenant = _fetch_tenant_detail(UUID(created["id"]))
    if not tenant:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Tenant creation failed")
    return tenant


@router.patch("/{tenant_id}", response_model=TenantDetail)
def update_tenant(
    tenant_id: UUID,
    payload: TenantUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_TENANT_WRITE_ROLES)),
) -> Dict[str, Any]:
    fields = []
    params: list = []

    for field_name in ("name", "status", "sla_level", "business_criticality", "timezone", "notes"):
        value = getattr(payload, field_name)
        if value is not None:
            fields.append(f"{field_name} = %s")
            params.append(value)

    if not fields:
        # Guarded already by TenantUpdateRequest's model_validator, kept
        # here too as defense in depth.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one field must be provided")

    params.append(str(tenant_id))
    query = f"UPDATE tenants SET {', '.join(fields)} WHERE id = %s RETURNING id::text;"

    updated = fetch_one_write(query, tuple(params))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant = _fetch_tenant_detail(UUID(updated["id"]))
    if not tenant:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Tenant update failed")
    return tenant
