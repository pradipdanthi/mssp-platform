"""
KB-010: Reusable FastAPI dependencies for authentication and RBAC.

get_current_user() and require_roles() are used by the new /auth/me
endpoint today. They are also written so that any future endpoint can
import and attach them with zero extra work.

require_tenant_match() is provided as part of the RBAC/tenant-isolation
foundation for future use. It is not yet attached to any endpoint - the
existing /admin/* and /customer/* preview endpoints are intentionally left
unauthenticated in this KB-010 phase (see AGENTS.md / CLAUDE.md).
"""

from typing import Any, Dict, Optional

from fastapi import Depends, Header, HTTPException, status

from app.core.security import decode_access_token
from app.services.auth_service import get_user_by_id


def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Verify the Authorization: Bearer <token> header and return the current,
    live database row for that user (never a stale copy from the token).

    Always raises HTTPException(401) for any kind of authentication
    failure (missing header, malformed header, expired token, invalid
    signature, unknown user id) - the exact reason is never revealed to the
    caller, only implicitly available via server-side logs.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1].strip()

    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    return user


def require_roles(*allowed_roles: str):
    """
    Dependency factory: attach to an endpoint to restrict it to specific
    roles, e.g. Depends(require_roles("platform_admin", "soc_manager")).
    """

    def _check_role(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return _check_role


def require_tenant_match(resolved_tenant_id: Optional[str], current_user: Dict[str, Any]) -> None:
    """
    Enforce tenant isolation for customer-role users.

    If current_user's role is customer_admin/customer_viewer and
    resolved_tenant_id does not match their own tenant_id, raise 404 (not
    403) - this way a customer cannot tell the difference between "this
    tenant belongs to someone else" and "this tenant does not exist",
    matching the existing 404 behavior already used for unknown tenants in
    app/main.py. platform_admin/soc_manager/soc_analyst are exempt by design.
    """
    if current_user.get("role") in ("customer_admin", "customer_viewer"):
        if str(current_user.get("tenant_id")) != str(resolved_tenant_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
