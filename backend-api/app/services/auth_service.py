"""
KB-010: Authentication business logic.

This module is the only place that reads platform_users.password_hash. It
never returns that column to a caller - to_public_user() below builds a
response object that has no password field at all.
"""

from typing import Any, Dict

from app.core.security import verify_password
from app.db.session import execute, fetch_one


class InvalidCredentialsError(Exception):
    """Raised when the email/password combination is not valid."""


class AccountNotActiveError(Exception):
    """Raised when the credentials are correct but the account is inactive or locked."""


def get_user_by_email(email: str) -> Dict[str, Any]:
    return fetch_one(
        """
        SELECT
            u.id::text,
            u.tenant_id::text,
            u.user_type,
            u.role,
            u.full_name,
            u.email,
            u.phone,
            u.status,
            u.password_hash,
            u.last_login_at,
            u.created_at,
            u.updated_at,
            t.short_code AS tenant_short_code,
            t.name AS tenant_name
        FROM platform_users u
        LEFT JOIN tenants t ON t.id = u.tenant_id
        WHERE lower(u.email) = lower(%s);
        """,
        (email,),
    )


def get_user_by_id(user_id: str) -> Dict[str, Any]:
    return fetch_one(
        """
        SELECT
            u.id::text,
            u.tenant_id::text,
            u.user_type,
            u.role,
            u.full_name,
            u.email,
            u.phone,
            u.status,
            u.password_hash,
            u.last_login_at,
            u.created_at,
            u.updated_at,
            t.short_code AS tenant_short_code,
            t.name AS tenant_name
        FROM platform_users u
        LEFT JOIN tenants t ON t.id = u.tenant_id
        WHERE u.id = %s;
        """,
        (user_id,),
    )


def _touch_last_login(user_id: str) -> None:
    execute(
        "UPDATE platform_users SET last_login_at = now() WHERE id = %s;",
        (user_id,),
    )


def authenticate_user(email: str, password: str) -> Dict[str, Any]:
    """
    Validate credentials and return the full user row (including
    password_hash) for internal use only. Raises InvalidCredentialsError or
    AccountNotActiveError on failure - callers must never reveal which of
    "email not found" or "wrong password" occurred.
    """
    user = get_user_by_email(email)

    if not user or not verify_password(password, user.get("password_hash")):
        raise InvalidCredentialsError("Invalid email or password")

    if user.get("status") != "active":
        raise AccountNotActiveError("Account is not active")

    _touch_last_login(user["id"])
    return get_user_by_id(user["id"])


def to_public_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """Build the safe, public representation of a user - never includes password_hash."""
    last_login_at = user.get("last_login_at")
    if last_login_at is not None and not isinstance(last_login_at, str):
        last_login_at = last_login_at.isoformat()

    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "user_type": user["user_type"],
        "role": user["role"],
        "tenant_id": user.get("tenant_id"),
        "tenant_short_code": user.get("tenant_short_code"),
        "tenant_name": user.get("tenant_name"),
        "status": user["status"],
        "last_login_at": last_login_at,
    }
