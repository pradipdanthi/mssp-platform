"""
KB-010: Authentication endpoints.

- POST /auth/login  - public, exchanges email+password for a JWT access token
- GET  /auth/me     - requires a valid token, returns the caller's own profile
- GET  /auth/roles  - public, static role catalog (no per-user data)

None of these endpoints ever return password_hash - UserPublic (see
app/schemas/auth.py) has no such field.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.security import create_access_token
from app.schemas.auth import (
    LoginRequest,
    RoleInfo,
    RolesResponse,
    TokenResponse,
    UserPublic,
)
from app.services.auth_service import (
    AccountNotActiveError,
    InvalidCredentialsError,
    authenticate_user,
    to_public_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])

ROLE_CATALOG: List[RoleInfo] = [
    RoleInfo(
        role="platform_admin",
        user_type="admin",
        cross_tenant=True,
        description="Full platform administrator. Can manage all tenants, users, and platform settings.",
    ),
    RoleInfo(
        role="soc_manager",
        user_type="admin",
        cross_tenant=True,
        description="SOC manager. Can view and manage alerts/incidents across all tenants and assign analysts.",
    ),
    RoleInfo(
        role="soc_analyst",
        user_type="admin",
        cross_tenant=True,
        description="SOC analyst. Can triage and work alerts/incidents across tenants as assigned.",
    ),
    RoleInfo(
        role="customer_admin",
        user_type="customer",
        cross_tenant=False,
        description="Customer administrator. Can view and manage their own organization's dashboard.",
    ),
    RoleInfo(
        role="customer_viewer",
        user_type="customer",
        cross_tenant=False,
        description="Customer viewer. Read-only access to their own organization's dashboard.",
    ),
]


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    try:
        user = authenticate_user(payload.email, payload.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    except AccountNotActiveError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    public_user = to_public_user(user)

    token_data = create_access_token(
        subject=public_user["id"],
        extra_claims={
            "role": public_user["role"],
            "user_type": public_user["user_type"],
            "tenant_id": public_user["tenant_id"],
        },
    )

    return TokenResponse(
        access_token=token_data["access_token"],
        token_type=token_data["token_type"],
        expires_in=token_data["expires_in"],
        user=UserPublic(**public_user),
    )


@router.get("/me", response_model=UserPublic)
def me(current_user: Dict[str, Any] = Depends(get_current_user)) -> UserPublic:
    return UserPublic(**to_public_user(current_user))


@router.get("/roles", response_model=RolesResponse)
def roles() -> RolesResponse:
    return RolesResponse(roles=ROLE_CATALOG)
