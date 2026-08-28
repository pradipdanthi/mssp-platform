"""
KB-010: Authentication endpoints.
KB-034: self-service profile update + password change.
KB-111 Phase 3: login rate limiting + TOTP MFA.

- POST /auth/login  - public, exchanges email+password for a JWT access token
- GET  /auth/me     - requires a valid token, returns the caller's own profile
- PATCH /auth/me    - update own full_name and/or phone only
- POST /auth/change-password - change own password (current + new)
- GET  /auth/roles  - public, static role catalog (no per-user data)
- POST /auth/mfa/setup - generate TOTP secret + otpauth URI
- POST /auth/mfa/verify - enable MFA after TOTP confirmation
- POST /auth/mfa/authenticate - complete login after MFA challenge

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
    LoginResponse,
    MfaAuthenticateRequest,
    MfaCompleteSetupRequest,
    MfaCompleteSetupResponse,
    MfaSetupResponse,
    MfaSetupSessionRequest,
    MfaVerifyRequest,
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
    change_own_password,
    get_user_by_id,
    to_public_user,
    update_own_profile_fields,
    verify_user_credentials,
    _touch_last_login,
)
from app.services.login_rate_limit import (
    LoginRateLimitExceeded,
    check_login_rate_limit,
    record_failed_login,
    reset_login_rate_limit,
)
from app.services.mfa_service import (
    authenticate_mfa_factor,
    begin_mfa_setup,
    complete_mfa_setup,
    complete_mfa_setup_with_recovery,
    get_mfa_setup_session,
    issue_mfa_pending_token,
    issue_mfa_setup_token,
    resolve_mfa_pending_token,
    resolve_mfa_setup_token,
    user_requires_mfa,
    user_requires_mfa_setup,
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


def _client_ip(request: Request) -> str | None:
    client_ip = None
    if request.client:
        client_ip = request.client.host
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()[:64]
    return client_ip


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


def _issue_login_token(user: Dict[str, Any], *, client_ip: str | None) -> TokenResponse:
    public_user = to_public_user(user)
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


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> LoginResponse:
    client_ip = _client_ip(request)
    email = payload.email.strip().lower()

    try:
        check_login_rate_limit(client_ip=client_ip, email=email)
    except LoginRateLimitExceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again in 15 minutes.",
        )

    try:
        user = verify_user_credentials(payload.email, payload.password)
    except InvalidCredentialsError:
        record_failed_login(client_ip=client_ip, email=email)
        write_audit_event(
            action="AUTH_LOGIN_FAILED",
            entity_type="auth",
            actor_email=email,
            source_ip=client_ip,
            action_status="FAILED",
            details={"email": email},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    except AccountNotActiveError:
        record_failed_login(client_ip=client_ip, email=email)
        write_audit_event(
            action="AUTH_LOGIN_FAILED",
            entity_type="auth",
            actor_email=email,
            source_ip=client_ip,
            action_status="FAILED",
            details={"email": email, "reason": "inactive"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    reset_login_rate_limit(client_ip=client_ip, email=email)

    public_user = to_public_user(user)
    _enforce_portal_login(public_user["role"], payload.portal, public_user.get("email"))

    if user_requires_mfa(user):
        return LoginResponse(
            mfa_required=True,
            mfa_token=issue_mfa_pending_token(user["id"]),
        )

    if user_requires_mfa_setup(user):
        begin_mfa_setup(user["id"])
        return LoginResponse(
            mfa_setup_required=True,
            setup_token=issue_mfa_setup_token(user["id"]),
        )

    _touch_last_login(user["id"])
    refreshed = get_user_by_id(user["id"])
    issued = _issue_login_token(refreshed, client_ip=client_ip)
    return LoginResponse(
        mfa_required=False,
        access_token=issued.access_token,
        token_type=issued.token_type,
        expires_in=issued.expires_in,
        user=issued.user.model_dump(),
    )


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(current_user: Dict[str, Any] = Depends(get_current_user)) -> MfaSetupResponse:
    try:
        result = begin_mfa_setup(current_user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MfaSetupResponse(**result)


@router.post("/mfa/verify")
def mfa_verify(
    payload: MfaVerifyRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    try:
        complete_mfa_setup(current_user["id"], payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_from_user(
        current_user,
        action="AUTH_MFA_ENABLED",
        entity_type="auth",
        details={"email": current_user.get("email")},
    )
    return {"status": "ok", "message": "MFA enabled"}


@router.post("/mfa/setup-session", response_model=MfaSetupResponse)
def mfa_setup_session(payload: MfaSetupSessionRequest) -> MfaSetupResponse:
    """Return QR/secret for mandatory first-login MFA enrollment."""
    try:
        user_id = resolve_mfa_setup_token(payload.setup_token)
        result = get_mfa_setup_session(user_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA setup session",
        ) from exc
    return MfaSetupResponse(**result)


@router.post("/mfa/complete-setup", response_model=MfaCompleteSetupResponse)
def mfa_complete_setup(payload: MfaCompleteSetupRequest, request: Request) -> MfaCompleteSetupResponse:
    """Complete mandatory MFA enrollment and issue recovery codes + session JWT."""
    client_ip = _client_ip(request)
    try:
        user_id = resolve_mfa_setup_token(payload.setup_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA setup session",
        ) from exc

    try:
        recovery_codes = complete_mfa_setup_with_recovery(user_id, payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    audit_from_user(
        {"id": user_id},
        action="AUTH_MFA_ENABLED",
        entity_type="auth",
        details={"recovery_codes_issued": len(recovery_codes), "mandatory_setup": True},
    )

    _touch_last_login(user_id)
    refreshed = get_user_by_id(user_id)
    issued = _issue_login_token(refreshed, client_ip=client_ip)
    return MfaCompleteSetupResponse(
        access_token=issued.access_token,
        token_type=issued.token_type,
        expires_in=issued.expires_in,
        user=issued.user,
        recovery_codes=recovery_codes,
    )


@router.post("/mfa/authenticate", response_model=TokenResponse)
def mfa_authenticate(payload: MfaAuthenticateRequest, request: Request) -> TokenResponse:
    client_ip = _client_ip(request)
    try:
        user_id = resolve_mfa_pending_token(payload.mfa_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA session",
        )

    user = get_user_by_id(user_id)
    if not user or not user_requires_mfa(user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA session",
        )
    ok, factor = authenticate_mfa_factor(user_id, user, payload.code)
    if not ok:
        write_audit_event(
            action="AUTH_LOGIN_FAILED",
            entity_type="auth",
            actor_user_id=user_id,
            actor_email=user.get("email"),
            source_ip=client_ip,
            action_status="FAILED",
            details={"reason": f"invalid_mfa_{factor}"},
        )
        detail = "Invalid recovery code" if factor == "recovery" else "Invalid MFA code"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )

    if factor == "recovery":
        audit_from_user(
            user,
            action="AUTH_MFA_RECOVERY_USED",
            entity_type="auth",
            tenant_id=user.get("tenant_id"),
            source_ip=client_ip,
            details={"email": user.get("email")},
        )

    _touch_last_login(user_id)
    refreshed = get_user_by_id(user_id)
    return _issue_login_token(refreshed, client_ip=client_ip)


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
