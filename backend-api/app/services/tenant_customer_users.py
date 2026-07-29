"""Shared tenant-scoped customer portal user operations (MSSP + customer self-service)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from psycopg.errors import UniqueViolation

from app.core.security import hash_password
from app.db.session import fetch_all, fetch_one, fetch_one_write
from app.services.audit_service import audit_from_user

CUSTOMER_PORTAL_ROLES = frozenset({"customer_admin", "customer_viewer"})
MSSP_STAFF_ROLES = frozenset({"platform_admin", "soc_manager", "soc_analyst"})
FORBIDDEN_CUSTOMER_ASSIGN_ROLES = MSSP_STAFF_ROLES

USER_CREATED = "USER_CREATED"
USER_ROLE_UPDATED = "USER_ROLE_UPDATED"
USER_DISABLED = "USER_DISABLED"
USER_DELETED = "USER_DELETED"
PASSWORD_RESET_FORCED = "PASSWORD_RESET_FORCED"

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


def assert_customer_role(role: str) -> None:
    if role not in CUSTOMER_PORTAL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be customer_admin or customer_viewer",
        )


def list_portal_users(tenant_id: str) -> List[Dict[str, Any]]:
    return fetch_all(
        f"""
        SELECT {_USER_COLS}
        FROM platform_users
        WHERE tenant_id = %s::uuid
          AND role IN ('customer_admin', 'customer_viewer')
        ORDER BY created_at DESC;
        """,
        (tenant_id,),
    )


def get_portal_user(tenant_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    return fetch_one(
        f"""
        SELECT {_USER_COLS}
        FROM platform_users
        WHERE id = %s::uuid AND tenant_id = %s::uuid
          AND role IN ('customer_admin', 'customer_viewer');
        """,
        (user_id, tenant_id),
    )


def _last_admin_guard(tenant_id: str, existing: Dict[str, Any], updates: Dict[str, Any]) -> None:
    if existing.get("role") != "customer_admin" or existing.get("status") != "active":
        return
    would_remove = updates.get("role") == "customer_viewer" or updates.get("status") in (
        "inactive",
        "locked",
    )
    if not would_remove:
        return
    admins = fetch_one(
        """
        SELECT count(*)::int AS c FROM platform_users
        WHERE tenant_id = %s::uuid AND role = 'customer_admin' AND status = 'active';
        """,
        (tenant_id,),
    )
    if int((admins or {}).get("c") or 0) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot demote or disable the last active customer administrator",
        )


def create_portal_user(
    *,
    tenant_id: str,
    email: str,
    full_name: str,
    password: str,
    role: str,
    phone: Optional[str],
    actor: Dict[str, Any],
    source_ip: Optional[str],
) -> Dict[str, Any]:
    assert_customer_role(role)
    try:
        row = fetch_one_write(
            f"""
            INSERT INTO platform_users (
                tenant_id, user_type, role, full_name, email, phone, status, password_hash
            )
            VALUES (%s::uuid, 'customer', %s, %s, %s, %s, 'active', %s)
            RETURNING {_USER_COLS};
            """,
            (tenant_id, role, full_name, email, phone, hash_password(password)),
        )
    except UniqueViolation:
        audit_from_user(
            actor,
            action=USER_CREATED,
            entity_type="platform_user",
            tenant_id=tenant_id,
            source_ip=source_ip,
            details={"email": email, "reason": "duplicate"},
            action_status="FAILED",
        )
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    if not row:
        raise HTTPException(status_code=500, detail="User create failed")
    audit_from_user(
        actor,
        action=USER_CREATED,
        entity_type="platform_user",
        entity_id=row["id"],
        tenant_id=tenant_id,
        source_ip=source_ip,
        details={"email": row["email"], "role": row["role"]},
    )
    return row


def update_portal_user(
    *,
    tenant_id: str,
    user_id: str,
    updates: Dict[str, Any],
    actor: Dict[str, Any],
    source_ip: Optional[str],
) -> Dict[str, Any]:
    existing = get_portal_user(tenant_id, user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    if updates.get("role"):
        assert_customer_role(str(updates["role"]))
    _last_admin_guard(tenant_id, existing, updates)
    if not updates:
        raise HTTPException(status_code=422, detail="At least one field must be provided")

    fields = [f"{k} = %s" for k in updates]
    params = list(updates.values()) + [user_id, tenant_id]
    row = fetch_one_write(
        f"""
        UPDATE platform_users
        SET {', '.join(fields)}, updated_at = now()
        WHERE id = %s::uuid AND tenant_id = %s::uuid
        RETURNING {_USER_COLS};
        """,
        tuple(params),
    )
    action = USER_ROLE_UPDATED if "role" in updates else "USER_UPDATED"
    if updates.get("status") in ("inactive", "locked"):
        action = USER_DISABLED
    elif updates.get("status") == "active":
        action = "USER_REACTIVATED"
    audit_from_user(
        actor,
        action=action,
        entity_type="platform_user",
        entity_id=user_id,
        tenant_id=tenant_id,
        source_ip=source_ip,
        details={"before": {"role": existing["role"], "status": existing["status"]}, "after": updates},
    )
    return row


def soft_delete_portal_user(
    *,
    tenant_id: str,
    user_id: str,
    actor: Dict[str, Any],
    source_ip: Optional[str],
) -> Dict[str, Any]:
    existing = get_portal_user(tenant_id, user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    _last_admin_guard(tenant_id, existing, {"status": "inactive"})
    row = fetch_one_write(
        f"""
        UPDATE platform_users
        SET status = 'inactive', updated_at = now()
        WHERE id = %s::uuid AND tenant_id = %s::uuid
        RETURNING {_USER_COLS};
        """,
        (user_id, tenant_id),
    )
    audit_from_user(
        actor,
        action=USER_DELETED,
        entity_type="platform_user",
        entity_id=user_id,
        tenant_id=tenant_id,
        source_ip=source_ip,
        details={"email": existing.get("email"), "mode": "soft_delete"},
    )
    return row or existing


def reset_portal_user_password(
    *,
    tenant_id: str,
    user_id: str,
    new_password: str,
    actor: Dict[str, Any],
    source_ip: Optional[str],
) -> None:
    existing = get_portal_user(tenant_id, user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    fetch_one_write(
        """
        UPDATE platform_users
        SET password_hash = %s, updated_at = now()
        WHERE id = %s::uuid AND tenant_id = %s::uuid;
        """,
        (hash_password(new_password), user_id, tenant_id),
    )
    audit_from_user(
        actor,
        action=PASSWORD_RESET_FORCED,
        entity_type="platform_user",
        entity_id=user_id,
        tenant_id=tenant_id,
        source_ip=source_ip,
        details={"email": existing.get("email")},
    )
