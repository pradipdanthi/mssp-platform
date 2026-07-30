"""KB-085: Customer portal tenant user management (customer_admin only for writes)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.dependencies import get_current_user, require_tenant_match
from app.core.security import hash_password
from app.db.session import fetch_all, fetch_one, fetch_one_write
from app.services.audit_service import audit_from_user
from app.services.list_pagination import clamp_pagination, pagination_meta

router = APIRouter(prefix="/customer", tags=["customer-users"])

CUSTOMER_ROLES = frozenset({"customer_admin", "customer_viewer"})
_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

_USER_COLS = """
    id::text,
    tenant_id::text,
    user_type,
    role,
    full_name,
    email,
    phone,
    status,
    last_login_at::text,
    created_at::text,
    updated_at::text
"""


class CustomerUserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL_RE)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["customer_admin", "customer_viewer"] = "customer_viewer"
    phone: Optional[str] = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def normalize(self) -> "CustomerUserCreate":
        self.email = self.email.strip().lower()
        self.full_name = self.full_name.strip()
        if self.phone is not None:
            self.phone = self.phone.strip() or None
        return self


class CustomerUserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=40)
    role: Optional[Literal["customer_admin", "customer_viewer"]] = None
    status: Optional[Literal["active", "inactive", "locked"]] = None


class CustomerUserPasswordUpdate(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return request.client.host
    return None


def _resolve_tenant(short_code: str, user: Dict[str, Any]) -> Dict[str, Any]:
    tenant = fetch_one(
        "SELECT id::text, short_code, name FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    require_tenant_match(tenant["id"], user)
    return tenant


def _require_customer_admin(user: Dict[str, Any]) -> None:
    if user.get("role") != "customer_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only customer administrators can manage users",
        )


@router.get("/users")
def list_customer_users_self(
    current_user: Dict[str, Any] = Depends(get_current_user),
    user_status: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> Dict[str, Any]:
    """List users for the authenticated customer's tenant (no short_code in path)."""
    if current_user.get("role") not in CUSTOMER_ROLES:
        raise HTTPException(status_code=403, detail="Customer role required")
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Customer tenant context required")
    page, page_size, offset = clamp_pagination(page, page_size)
    where = [
        "tenant_id = %s::uuid",
        "role IN ('customer_admin', 'customer_viewer')",
    ]
    params: list = [str(tenant_id)]
    st = (user_status or "").strip().lower()
    if st in ("active", "inactive", "locked"):
        where.append("status = %s")
        params.append(st)
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "full_name ILIKE %s OR "
            "email ILIKE %s OR "
            "role ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like])
    where_sql = " AND ".join(where)
    count_row = fetch_one(
        f"SELECT count(*)::int AS total FROM platform_users WHERE {where_sql};",
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)
    rows = fetch_all(
        f"""
        SELECT {_USER_COLS}
        FROM platform_users
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return {"users": rows, **pagination_meta(total, page, page_size)}


@router.get("/users/{short_code}")
def list_customer_users(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    user_status: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> Dict[str, Any]:
    if current_user.get("role") not in CUSTOMER_ROLES:
        raise HTTPException(status_code=403, detail="Customer role required")
    tenant = _resolve_tenant(short_code, current_user)
    page, page_size, offset = clamp_pagination(page, page_size)
    where = [
        "tenant_id = %s::uuid",
        "role IN ('customer_admin', 'customer_viewer')",
    ]
    params: list = [tenant["id"]]
    st = (user_status or "").strip().lower()
    if st in ("active", "inactive", "locked"):
        where.append("status = %s")
        params.append(st)
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "full_name ILIKE %s OR "
            "email ILIKE %s OR "
            "role ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like])
    where_sql = " AND ".join(where)
    count_row = fetch_one(
        f"SELECT count(*)::int AS total FROM platform_users WHERE {where_sql};",
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)
    rows = fetch_all(
        f"""
        SELECT {_USER_COLS}
        FROM platform_users
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return {"users": rows, **pagination_meta(total, page, page_size)}


@router.post("/users/{short_code}", status_code=status.HTTP_201_CREATED)
def create_customer_user(
    short_code: str,
    payload: CustomerUserCreate,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_customer_admin(current_user)
    tenant = _resolve_tenant(short_code, current_user)
    try:
        row = fetch_one_write(
            f"""
            INSERT INTO platform_users (
                tenant_id, user_type, role, full_name, email, phone, status, password_hash
            )
            VALUES (%s::uuid, 'customer', %s, %s, %s, %s, 'active', %s)
            RETURNING {_USER_COLS};
            """,
            (
                tenant["id"],
                payload.role,
                payload.full_name,
                payload.email,
                payload.phone,
                hash_password(payload.password),
            ),
        )
    except UniqueViolation:
        audit_from_user(
            current_user,
            action="USER_CREATE",
            entity_type="platform_user",
            tenant_id=tenant["id"],
            source_ip=_client_ip(request),
            details={"email": payload.email, "reason": "duplicate"},
            action_status="FAILED",
        )
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    if not row:
        raise HTTPException(status_code=500, detail="User create failed")
    audit_from_user(
        current_user,
        action="USER_CREATE",
        entity_type="platform_user",
        entity_id=row["id"],
        tenant_id=tenant["id"],
        source_ip=_client_ip(request),
        details={"email": row["email"], "role": row["role"]},
    )
    return row


@router.patch("/users/{short_code}/{user_id}")
def update_customer_user(
    short_code: str,
    user_id: UUID,
    payload: CustomerUserUpdate,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_customer_admin(current_user)
    tenant = _resolve_tenant(short_code, current_user)
    existing = fetch_one(
        f"""
        SELECT {_USER_COLS}
        FROM platform_users
        WHERE id = %s::uuid AND tenant_id = %s::uuid
          AND role IN ('customer_admin', 'customer_viewer');
        """,
        (str(user_id), tenant["id"]),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    updates: Dict[str, Any] = {}
    if payload.full_name is not None:
        updates["full_name"] = payload.full_name.strip()
    if "phone" in payload.model_fields_set:
        updates["phone"] = (payload.phone or "").strip() or None
    if payload.role is not None:
        updates["role"] = payload.role
    if payload.status is not None:
        updates["status"] = payload.status
    if not updates:
        raise HTTPException(status_code=422, detail="At least one field must be provided")

    if updates.get("role") == "customer_viewer" or updates.get("status") in ("inactive", "locked"):
        if existing["role"] == "customer_admin" and existing["status"] == "active":
            admins = fetch_one(
                """
                SELECT count(*)::int AS c FROM platform_users
                WHERE tenant_id = %s::uuid AND role = 'customer_admin' AND status = 'active';
                """,
                (tenant["id"],),
            )
            if int((admins or {}).get("c") or 0) <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot demote or disable the last active customer administrator",
                )

    fields = [f"{k} = %s" for k in updates]
    params = list(updates.values()) + [str(user_id), tenant["id"]]
    row = fetch_one_write(
        f"""
        UPDATE platform_users
        SET {', '.join(fields)}
        WHERE id = %s::uuid AND tenant_id = %s::uuid
        RETURNING {_USER_COLS};
        """,
        tuple(params),
    )
    audit_from_user(
        current_user,
        action="USER_UPDATE" if "role" not in updates else "USER_ROLE_CHANGE",
        entity_type="platform_user",
        entity_id=str(user_id),
        tenant_id=tenant["id"],
        source_ip=_client_ip(request),
        details={"before": existing, "after": updates},
    )
    return row


@router.patch("/users/{short_code}/{user_id}/password")
def set_customer_user_password(
    short_code: str,
    user_id: UUID,
    payload: CustomerUserPasswordUpdate,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    _require_customer_admin(current_user)
    tenant = _resolve_tenant(short_code, current_user)
    existing = fetch_one(
        """
        SELECT id::text FROM platform_users
        WHERE id = %s::uuid AND tenant_id = %s::uuid
          AND role IN ('customer_admin', 'customer_viewer');
        """,
        (str(user_id), tenant["id"]),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    fetch_one_write(
        """
        UPDATE platform_users
        SET password_hash = %s, updated_at = now()
        WHERE id = %s::uuid AND tenant_id = %s::uuid
        RETURNING id::text;
        """,
        (hash_password(payload.new_password), str(user_id), tenant["id"]),
    )
    audit_from_user(
        current_user,
        action="USER_PASSWORD_RESET",
        entity_type="platform_user",
        entity_id=str(user_id),
        tenant_id=tenant["id"],
        source_ip=_client_ip(request),
        details={"target_user_id": str(user_id)},
    )
    return {"status": "updated"}
