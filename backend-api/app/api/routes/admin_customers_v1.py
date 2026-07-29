"""KB-085: Alias POST/GET /v1/admin/customers → tenant onboarding."""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import require_roles
from app.api.routes.tenant_management import (
    ADMIN_TENANT_WRITE_ROLES,
    create_tenant,
    get_tenant_detail,
)
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_all
from app.schemas.tenants import TenantCreateRequest, TenantDetail

router = APIRouter(prefix="/v1/admin/customers", tags=["v1-admin-customers"])


@router.post("", response_model=TenantDetail, status_code=201)
def create_customer(
    payload: TenantCreateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_TENANT_WRITE_ROLES)),
) -> Dict[str, Any]:
    """Atomic-style onboard: tenant + first customer_admin (via existing create_tenant)."""
    return create_tenant(payload, current_user)


@router.get("")
def list_customers(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    rows = fetch_all(
        """
        SELECT id::text, name, short_code, status, sla_level,
               primary_contact_email, primary_contact_phone, created_at::text
        FROM tenants
        ORDER BY created_at DESC;
        """
    )
    return {"customers": rows}


@router.get("/{tenant_id}", response_model=TenantDetail)
def get_customer(
    tenant_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    return get_tenant_detail(tenant_id, current_user)
