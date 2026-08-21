"""
V1 delegated customer user management (Gemini / KB-088 spec).

Customer: /v1/customer/users*
MSSP:       /v1/admin/customers/{tenant_id}/users*
(Proxied as /api/v1/... from nginx.)
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator

from app.api.dependencies import get_current_user, require_roles
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_one
from app.services import tenant_customer_users as tcu
from app.services.audit_service import audit_from_user

MSSP_CUSTOMER_USER_ROLES = ("platform_admin", "soc_manager")

customer_router = APIRouter(prefix="/v1/customer", tags=["v1-customer-users"])
admin_router = APIRouter(prefix="/v1/admin/customers", tags=["v1-admin-customer-users"])

_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class V1UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL_RE)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["customer_admin", "customer_viewer"] = "customer_viewer"
    phone: Optional[str] = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def normalize(self) -> "V1UserCreate":
        self.email = self.email.strip().lower()
        self.full_name = self.full_name.strip()
        if self.phone is not None:
            self.phone = self.phone.strip() or None
        return self


class V1UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=40)
    role: Optional[Literal["customer_admin", "customer_viewer"]] = None
    status: Optional[Literal["active", "inactive", "locked"]] = None


class V1PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return request.client.host
    return None


def _tenant_id_from_user(user: Dict[str, Any]) -> str:
    tid = user.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=403, detail="Customer tenant context required")
    return str(tid)


def _require_customer_admin(user: Dict[str, Any]) -> None:
    if user.get("role") != "customer_admin":
        raise HTTPException(status_code=403, detail="Only customer administrators can manage users")


def _assert_tenant_exists(tenant_id: str) -> None:
    if not fetch_one("SELECT id::text FROM tenants WHERE id = %s::uuid;", (tenant_id,)):
        raise HTTPException(status_code=404, detail="Tenant not found")


def _audit_v1_user(
    current_user: Dict[str, Any],
    request: Request,
    *,
    action: str,
    tenant_id: str,
    entity_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    action_status: str = "SUCCESS",
) -> None:
    payload = dict(details or {})
    payload.setdefault("outcome", action_status)
    audit_from_user(
        current_user,
        action=action,
        entity_type="platform_user",
        entity_id=entity_id,
        tenant_id=tenant_id,
        source_ip=_client_ip(request),
        details=payload,
        action_status=action_status,
    )


def _updates_from_payload(payload: V1UserUpdate) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}
    if payload.full_name is not None:
        updates["full_name"] = payload.full_name.strip()
    if "phone" in payload.model_fields_set:
        updates["phone"] = (payload.phone or "").strip() or None
    if payload.role is not None:
        updates["role"] = payload.role
    if payload.status is not None:
        updates["status"] = payload.status
    return updates


# --- Customer self-service ---


@customer_router.get("/users")
def v1_list_customer_users(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, List[Dict[str, Any]]]:
    if current_user.get("role") not in tcu.CUSTOMER_PORTAL_ROLES:
        raise HTTPException(status_code=403, detail="Customer role required")
    tenant_id = _tenant_id_from_user(current_user)
    return {"users": tcu.list_portal_users(tenant_id)}


@customer_router.post("/users", status_code=status.HTTP_201_CREATED)
def v1_create_customer_user(
    payload: V1UserCreate,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_customer_admin(current_user)
    tenant_id = _tenant_id_from_user(current_user)
    try:
        row = tcu.create_portal_user(
            tenant_id=tenant_id,
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
            role=payload.role,
            phone=payload.phone,
            actor=current_user,
            source_ip=_client_ip(request),
        )
    except HTTPException as exc:
        _audit_v1_user(
            current_user,
            request,
            action="V1_CUSTOMER_USER_CREATED",
            tenant_id=tenant_id,
            details={"email": payload.email, "role": payload.role, "http_status": exc.status_code},
            action_status="FAILED",
        )
        raise
    _audit_v1_user(
        current_user,
        request,
        action="V1_CUSTOMER_USER_CREATED",
        tenant_id=tenant_id,
        entity_id=row["id"],
        details={"email": row["email"], "role": row["role"]},
    )
    return row


@customer_router.put("/users/{user_id}")
def v1_update_customer_user_put(
    user_id: UUID,
    payload: V1UserUpdate,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return v1_update_customer_user(user_id, payload, request, current_user)


@customer_router.patch("/users/{user_id}")
def v1_update_customer_user(
    user_id: UUID,
    payload: V1UserUpdate,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_customer_admin(current_user)
    tenant_id = _tenant_id_from_user(current_user)
    updates = _updates_from_payload(payload)
    if not updates:
        raise HTTPException(status_code=422, detail="At least one field must be provided")
    try:
        row = tcu.update_portal_user(
            tenant_id=tenant_id,
            user_id=str(user_id),
            updates=updates,
            actor=current_user,
            source_ip=_client_ip(request),
        )
    except HTTPException as exc:
        _audit_v1_user(
            current_user,
            request,
            action="V1_CUSTOMER_USER_UPDATED",
            tenant_id=tenant_id,
            entity_id=str(user_id),
            details={"http_status": exc.status_code, "fields": sorted(updates.keys())},
            action_status="FAILED",
        )
        raise
    _audit_v1_user(
        current_user,
        request,
        action="V1_CUSTOMER_USER_UPDATED",
        tenant_id=tenant_id,
        entity_id=str(user_id),
        details={"fields": sorted(updates.keys())},
    )
    return row


@customer_router.delete("/users/{user_id}")
def v1_delete_customer_user(
    user_id: UUID,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    _require_customer_admin(current_user)
    tenant_id = _tenant_id_from_user(current_user)
    try:
        tcu.soft_delete_portal_user(
            tenant_id=tenant_id,
            user_id=str(user_id),
            actor=current_user,
            source_ip=_client_ip(request),
        )
    except HTTPException as exc:
        _audit_v1_user(
            current_user,
            request,
            action="V1_CUSTOMER_USER_DELETED",
            tenant_id=tenant_id,
            entity_id=str(user_id),
            details={"http_status": exc.status_code},
            action_status="FAILED",
        )
        raise
    _audit_v1_user(
        current_user,
        request,
        action="V1_CUSTOMER_USER_DELETED",
        tenant_id=tenant_id,
        entity_id=str(user_id),
    )
    return {"status": "deleted"}


@customer_router.post("/users/{user_id}/reset-password")
def v1_customer_reset_password(
    user_id: UUID,
    payload: V1PasswordReset,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    _require_customer_admin(current_user)
    tenant_id = _tenant_id_from_user(current_user)
    try:
        tcu.reset_portal_user_password(
            tenant_id=tenant_id,
            user_id=str(user_id),
            new_password=payload.new_password,
            actor=current_user,
            source_ip=_client_ip(request),
        )
    except HTTPException as exc:
        _audit_v1_user(
            current_user,
            request,
            action="V1_CUSTOMER_PASSWORD_RESET",
            tenant_id=tenant_id,
            entity_id=str(user_id),
            details={"http_status": exc.status_code},
            action_status="FAILED",
        )
        raise
    _audit_v1_user(
        current_user,
        request,
        action="V1_CUSTOMER_PASSWORD_RESET",
        tenant_id=tenant_id,
        entity_id=str(user_id),
    )
    return {"status": "updated"}


# --- MSSP governance ---


@admin_router.get("/{tenant_id}/users")
def v1_admin_list_customer_users(
    tenant_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*MSSP_CUSTOMER_USER_ROLES)),
) -> Dict[str, List[Dict[str, Any]]]:
    _ = current_user
    tid = str(tenant_id)
    _assert_tenant_exists(tid)
    return {"users": tcu.list_portal_users(tid)}


@admin_router.post("/{tenant_id}/users", status_code=status.HTTP_201_CREATED)
def v1_admin_create_customer_user(
    tenant_id: UUID,
    payload: V1UserCreate,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles(*MSSP_CUSTOMER_USER_ROLES)),
) -> Dict[str, Any]:
    tid = str(tenant_id)
    _assert_tenant_exists(tid)
    try:
        row = tcu.create_portal_user(
            tenant_id=tid,
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
            role=payload.role,
            phone=payload.phone,
            actor=current_user,
            source_ip=_client_ip(request),
        )
    except HTTPException as exc:
        _audit_v1_user(
            current_user,
            request,
            action="V1_ADMIN_CUSTOMER_USER_CREATED",
            tenant_id=tid,
            details={"email": payload.email, "role": payload.role, "http_status": exc.status_code},
            action_status="FAILED",
        )
        raise
    _audit_v1_user(
        current_user,
        request,
        action="V1_ADMIN_CUSTOMER_USER_CREATED",
        tenant_id=tid,
        entity_id=row["id"],
        details={"email": row["email"], "role": row["role"]},
    )
    return row


@admin_router.put("/{tenant_id}/users/{user_id}")
def v1_admin_update_customer_user_put(
    tenant_id: UUID,
    user_id: UUID,
    payload: V1UserUpdate,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles(*MSSP_CUSTOMER_USER_ROLES)),
) -> Dict[str, Any]:
    return v1_admin_update_customer_user(tenant_id, user_id, payload, request, current_user)


@admin_router.patch("/{tenant_id}/users/{user_id}")
def v1_admin_update_customer_user(
    tenant_id: UUID,
    user_id: UUID,
    payload: V1UserUpdate,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles(*MSSP_CUSTOMER_USER_ROLES)),
) -> Dict[str, Any]:
    tid = str(tenant_id)
    _assert_tenant_exists(tid)
    updates = _updates_from_payload(payload)
    if not updates:
        raise HTTPException(status_code=422, detail="At least one field must be provided")
    try:
        row = tcu.update_portal_user(
            tenant_id=tid,
            user_id=str(user_id),
            updates=updates,
            actor=current_user,
            source_ip=_client_ip(request),
        )
    except HTTPException as exc:
        _audit_v1_user(
            current_user,
            request,
            action="V1_ADMIN_CUSTOMER_USER_UPDATED",
            tenant_id=tid,
            entity_id=str(user_id),
            details={"http_status": exc.status_code, "fields": sorted(updates.keys())},
            action_status="FAILED",
        )
        raise
    _audit_v1_user(
        current_user,
        request,
        action="V1_ADMIN_CUSTOMER_USER_UPDATED",
        tenant_id=tid,
        entity_id=str(user_id),
        details={"fields": sorted(updates.keys())},
    )
    return row


@admin_router.delete("/{tenant_id}/users/{user_id}")
def v1_admin_delete_customer_user(
    tenant_id: UUID,
    user_id: UUID,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles(*MSSP_CUSTOMER_USER_ROLES)),
) -> Dict[str, str]:
    tid = str(tenant_id)
    _assert_tenant_exists(tid)
    try:
        tcu.soft_delete_portal_user(
            tenant_id=tid,
            user_id=str(user_id),
            actor=current_user,
            source_ip=_client_ip(request),
        )
    except HTTPException as exc:
        _audit_v1_user(
            current_user,
            request,
            action="V1_ADMIN_CUSTOMER_USER_DELETED",
            tenant_id=tid,
            entity_id=str(user_id),
            details={"http_status": exc.status_code},
            action_status="FAILED",
        )
        raise
    _audit_v1_user(
        current_user,
        request,
        action="V1_ADMIN_CUSTOMER_USER_DELETED",
        tenant_id=tid,
        entity_id=str(user_id),
    )
    return {"status": "deleted"}


@admin_router.post("/{tenant_id}/users/{user_id}/reset-password")
def v1_admin_reset_customer_password(
    tenant_id: UUID,
    user_id: UUID,
    payload: V1PasswordReset,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles(*MSSP_CUSTOMER_USER_ROLES)),
) -> Dict[str, str]:
    tid = str(tenant_id)
    _assert_tenant_exists(tid)
    try:
        tcu.reset_portal_user_password(
            tenant_id=tid,
            user_id=str(user_id),
            new_password=payload.new_password,
            actor=current_user,
            source_ip=_client_ip(request),
        )
    except HTTPException as exc:
        _audit_v1_user(
            current_user,
            request,
            action="V1_ADMIN_CUSTOMER_PASSWORD_RESET",
            tenant_id=tid,
            entity_id=str(user_id),
            details={"http_status": exc.status_code},
            action_status="FAILED",
        )
        raise
    _audit_v1_user(
        current_user,
        request,
        action="V1_ADMIN_CUSTOMER_PASSWORD_RESET",
        tenant_id=tid,
        entity_id=str(user_id),
    )
    return {"status": "updated"}


router = APIRouter()
router.include_router(customer_router)
router.include_router(admin_router)
