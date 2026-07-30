"""
KB-014: Admin User Management API Foundation.

New endpoints under /admin/users/*:

- GET   /admin/users               - list all users
- GET   /admin/users/{user_id}     - single user detail
- POST  /admin/users               - create a user (bcrypt password hash)
- PATCH /admin/users/{user_id}          - update full_name/phone/status only
- PATCH /admin/users/{user_id}/password - admin-triggered password set

RBAC (approved decision A): platform_admin, soc_manager, and soc_analyst can
all GET (list/detail) - same read tier as ADMIN_SOC_ROLES imported from
admin.py. Only platform_admin can POST/PATCH/set a password. Customer roles
get 403 on all 5 endpoints, same as unauthenticated requests get 401.

There is intentionally no DELETE endpoint (approved decision, see KB-014
planning notes): platform_users.id is referenced with ON DELETE SET NULL
from incidents.assigned_to_user_id, incident_timeline.created_by_user_id,
incident_comments.created_by_user_id, appliance_activation_tokens.created_by_user_id,
and audit_logs.actor_user_id - a hard delete would silently strip the
attribution off that historical/audit data. Disabling a user is done via
PATCH {"status": "inactive"} or {"status": "locked"} instead, which also
immediately blocks that user's login and any of their already-issued but
still-valid tokens, because app/api/dependencies.py's get_current_user()
re-checks status against the live database on every request.

user_id is a UUID path parameter, validated by FastAPI/Pydantic before it
ever reaches a database query - an invalid UUID never produces a raw
database error, only a clean 422. Every response is built from UserDetail,
which has no password/password_hash field, and every SQL query in this
file deliberately never selects password_hash at all.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg.errors import UniqueViolation

from app.api.dependencies import require_roles
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.core.security import hash_password
from app.db.session import fetch_all, fetch_one, fetch_one_write
from app.schemas.users import (
    ADMIN_ROLES,
    CUSTOMER_ROLES,
    UserCreateRequest,
    UserDetail,
    UserPasswordUpdateRequest,
    UsersListResponse,
    UserUpdateRequest,
)
from app.services.list_pagination import clamp_pagination, pagination_meta

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

# KB-014: only platform_admin may create, update, or set a password for a
# user. soc_manager and soc_analyst keep read-only access (ADMIN_SOC_ROLES,
# imported from admin.py) for list/detail, same as tenant management.
ADMIN_USER_WRITE_ROLES = ("platform_admin",)

_USER_DETAIL_COLUMNS = """
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


def _fetch_user_detail(user_id: UUID) -> Optional[Dict[str, Any]]:
    row = fetch_one(
        f"SELECT {_USER_DETAIL_COLUMNS} FROM platform_users WHERE id = %s;",
        (str(user_id),),
    )
    return row or None


@router.get("", response_model=UsersListResponse)
def list_users(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
    scope: str = Query(default="staff", pattern="^(staff|all)$"),
    user_status: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, max_length=200, description="Search name/email/role"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> Dict[str, Any]:
    """
    Default scope=staff: platform personnel only (platform_admin, soc_manager, soc_analyst).
    Customer users are listed under /admin/tenants/{tenant_id}/users.
    Pass scope=all for legacy full listing (SOC tooling only).
    """
    _ = current_user
    page, page_size, offset = clamp_pagination(page, page_size)
    where: list[str] = []
    params: list = []
    if (scope or "staff").lower() != "all":
        where.append("role IN ('platform_admin', 'soc_manager', 'soc_analyst')")
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
            "role ILIKE %s OR "
            "COALESCE(phone, '') ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like, like])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    count_row = fetch_one(
        f"SELECT count(*)::int AS total FROM platform_users {where_sql};",
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)
    rows = fetch_all(
        f"""
        SELECT {_USER_DETAIL_COLUMNS}
        FROM platform_users
        {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return {"users": rows, **pagination_meta(total, page, page_size)}


@router.get("/{user_id}", response_model=UserDetail)
def get_user_detail(
    user_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    user = _fetch_user_detail(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("", response_model=UserDetail, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_USER_WRITE_ROLES)),
) -> Dict[str, Any]:
    # user_type is always derived server-side from role - never accepted as
    # input - so a role/user_type mismatch can never be submitted.
    user_type = "admin" if payload.role in ADMIN_ROLES else "customer"

    tenant_id_str = str(payload.tenant_id) if payload.tenant_id is not None else None

    if tenant_id_str is not None:
        # payload.role in CUSTOMER_ROLES is guaranteed here by
        # UserCreateRequest's model_validator (tenant_id is only ever
        # non-None for customer roles).
        tenant_exists = fetch_one("SELECT id FROM tenants WHERE id = %s;", (tenant_id_str,))
        if not tenant_exists:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="tenant_id does not reference an existing tenant",
            )

    existing = fetch_one(
        "SELECT id FROM platform_users WHERE email = %s;",
        (payload.email,),
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    password_hash = hash_password(payload.password)

    try:
        created = fetch_one_write(
            """
            INSERT INTO platform_users (tenant_id, user_type, role, full_name, email, phone, status, password_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id::text;
            """,
            (
                tenant_id_str,
                user_type,
                payload.role,
                payload.full_name,
                payload.email,
                payload.phone,
                payload.status,
                password_hash,
            ),
        )
    except UniqueViolation:
        # Race-condition backstop: two concurrent requests could both pass
        # the SELECT check above before either INSERT commits.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = _fetch_user_detail(UUID(created["id"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User creation failed")
    return user


@router.patch("/{user_id}", response_model=UserDetail)
def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_USER_WRITE_ROLES)),
) -> Dict[str, Any]:
    fields = []
    params: list = []

    # KB-014 scope only: full_name, phone, status. No email/role/tenant_id.
    for field_name in ("full_name", "phone", "status"):
        value = getattr(payload, field_name)
        if value is not None:
            fields.append(f"{field_name} = %s")
            params.append(value)

    if not fields:
        # Guarded already by UserUpdateRequest's model_validator, kept here
        # too as defense in depth.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one field must be provided")

    params.append(str(user_id))
    query = f"UPDATE platform_users SET {', '.join(fields)} WHERE id = %s RETURNING id::text;"

    updated = fetch_one_write(query, tuple(params))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user = _fetch_user_detail(UUID(updated["id"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User update failed")
    return user


@router.patch("/{user_id}/password", response_model=UserDetail)
def update_user_password(
    user_id: UUID,
    payload: UserPasswordUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_USER_WRITE_ROLES)),
) -> Dict[str, Any]:
    password_hash = hash_password(payload.new_password)

    updated = fetch_one_write(
        "UPDATE platform_users SET password_hash = %s WHERE id = %s RETURNING id::text;",
        (password_hash, str(user_id)),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user = _fetch_user_detail(UUID(updated["id"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Password update failed")
    return user
