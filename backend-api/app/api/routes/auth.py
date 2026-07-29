"""
KB-010: Authentication endpoints.
KB-034: self-service profile update + password change.

- POST /auth/login  - public, exchanges email+password for a JWT access token
- GET  /auth/me     - requires a valid token, returns the caller's own profile
- PATCH /auth/me    - update own full_name and/or phone only
- POST /auth/change-password - change own password (current + new)
- GET  /auth/roles  - public, static role catalog (no per-user data)

None of these endpoints ever return password_hash - UserPublic (see
app/schemas/auth.py) has no such field.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_current_user
from app.core.security import create_access_token
from app.schemas.auth import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    ProfileUpdateRequest,
    RoleInfo,
    RolesResponse,
    TokenResponse,
    UserPublic,
)
from app.services.audit_service import audit_from_user, write_audit_event
from app.services.auth_service import (
    AccountNotActiveError,
    InvalidCredentialsError,
    authenticate_user,
    change_own_password,
    to_public_user,
    update_own_profile_fields,
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


ADMIN_PORTAL_ROLES = frozenset({"platform_admin", "soc_manager", "soc_analyst"})
CUSTOMER_PORTAL_ROLES = frozenset({"customer_admin", "customer_viewer"})


def _enforce_portal_login(role: str, portal: str | None, email: str | None = None) -> None:
    if not portal:
        return
    if portal == "admin" and role not in ADMIN_PORTAL_ROLES:
        write_audit_event(
            action="AUTH_LOGIN_FAILED",
            entity_type="auth",
            actor_email=email,
            action_status="FAILED",
            details={"reason": "wrong_portal_admin", "role": role, "portal": portal},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is for the customer portal only. Use the customer portal (port 3001), not the MSSP admin console.",
        )
    if portal == "customer" and role not in CUSTOMER_PORTAL_ROLES:
        write_audit_event(
            action="AUTH_LOGIN_FAILED",
            entity_type="auth",
            actor_email=email,
            action_status="FAILED",
            details={"reason": "wrong_portal_customer", "role": role, "portal": portal},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MSSP staff must sign in on the admin portal (port 3000), not the customer portal.",
        )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request) -> TokenResponse:
    client_ip = None
    if request.client:
        client_ip = request.client.host
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()[:64]

    try:
        user = authenticate_user(payload.email, payload.password)
    except InvalidCredentialsError:
        write_audit_event(
            action="AUTH_LOGIN_FAILED",
            entity_type="auth",
            actor_email=payload.email.strip().lower(),
            source_ip=client_ip,
            action_status="FAILED",
            details={"email": payload.email.strip().lower()},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    except AccountNotActiveError:
        write_audit_event(
            action="AUTH_LOGIN_FAILED",
            entity_type="auth",
            actor_email=payload.email.strip().lower(),
            source_ip=client_ip,
            action_status="FAILED",
            details={"email": payload.email.strip().lower(), "reason": "inactive"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    public_user = to_public_user(user)
    _enforce_portal_login(public_user["role"], payload.portal, public_user.get("email"))

    token_data = create_access_token(
        subject=public_user["id"],
        extra_claims={
            "role": public_user["role"],
            "user_type": public_user["user_type"],
            "tenant_id": public_user["tenant_id"],
        },
    )

    audit_from_user(
        public_user,
        action="AUTH_LOGIN",
        entity_type="auth",
        tenant_id=public_user.get("tenant_id"),
        source_ip=client_ip,
        details={"email": public_user.get("email")},
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


@router.patch("/me", response_model=UserPublic)
def update_me(
    payload: ProfileUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> UserPublic:
    """
    KB-034: authenticated caller may update full_name and/or phone only.
    Email, role, tenant_id, status, and password cannot be changed here.
    """
    # model_dump(exclude_unset=True) tells us whether phone was sent (including null).
    raw = payload.model_dump(exclude_unset=True)
    updated = update_own_profile_fields(
        current_user["id"],
        full_name=payload.full_name,
        phone=payload.phone,
        update_phone="phone" in raw,
    )
    return UserPublic(**to_public_user(updated))


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    payload: ChangePasswordRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ChangePasswordResponse:
    """
    KB-034: self-service password change. Requires current password.
    Never returns password material.
    """
    try:
        change_own_password(
            current_user["id"],
            payload.current_password,
            payload.new_password,
        )
    except InvalidCredentialsError:
        audit_from_user(
            current_user,
            action="AUTH_PASSWORD_CHANGE",
            entity_type="auth",
            action_status="FAILED",
            details={"reason": "bad_current_password"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
    except AccountNotActiveError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    audit_from_user(
        current_user,
        action="AUTH_PASSWORD_CHANGE",
        entity_type="auth",
        details={"email": current_user.get("email")},
    )
    return ChangePasswordResponse()


@router.get("/roles", response_model=RolesResponse)
def roles() -> RolesResponse:
    return RolesResponse(roles=ROLE_CATALOG)
