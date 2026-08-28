"""
KB-010: Request/response models for the /auth/* endpoints.

UserPublic intentionally has no password/hash field at all - it is
structurally impossible for a password hash to leak through this model,
because the field simply does not exist on it.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)
    # admin (:3000) vs customer (:3001). When set, wrong portal roles are rejected at login.
    portal: Optional[Literal["admin", "customer"]] = None


class UserPublic(BaseModel):
    id: str
    email: str
    full_name: str
    user_type: str
    role: str
    tenant_id: Optional[str] = None
    # KB-021: customer portal uses short_code for /customer/{short_code}
    # paths. Null for platform/SOC users (and any account without a tenant).
    tenant_short_code: Optional[str] = None
    tenant_name: Optional[str] = None
    subscription_tier: Optional[str] = None
    status: str
    last_login_at: Optional[str] = None
    # KB-034: optional contact phone; never a secret.
    phone: Optional[str] = None
    is_mfa_enabled: bool = False


class LoginResponse(BaseModel):
    """Unified login response for password-only, MFA-challenge, and MFA-setup flows."""

    mfa_required: bool = False
    mfa_setup_required: bool = False
    mfa_token: Optional[str] = None
    setup_token: Optional[str] = None
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    expires_in: Optional[int] = None
    user: Optional[Dict[str, Any]] = None


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=8)


class MfaAuthenticateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mfa_token: str = Field(min_length=10, max_length=4096)
    code: str = Field(min_length=6, max_length=16)


class MfaSetupSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    setup_token: str = Field(min_length=10, max_length=4096)


class MfaCompleteSetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    setup_token: str = Field(min_length=10, max_length=4096)
    code: str = Field(min_length=6, max_length=8)


class ProfileUpdateRequest(BaseModel):
    """KB-034: caller may update only full_name and/or phone."""

    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ProfileUpdateRequest":
        if self.full_name is None and self.phone is None:
            raise ValueError("Provide full_name and/or phone to update")
        if self.full_name is not None:
            cleaned = self.full_name.strip()
            if not cleaned:
                raise ValueError("full_name cannot be blank")
            self.full_name = cleaned
        if self.phone is not None:
            cleaned_phone = self.phone.strip()
            self.phone = cleaned_phone if cleaned_phone else None
        return self


class ChangePasswordRequest(BaseModel):
    """KB-034: self-service password change. Never echoed back in responses."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class ChangePasswordResponse(BaseModel):
    status: str = "ok"
    message: str = "Password updated"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserPublic


class MfaCompleteSetupResponse(TokenResponse):
    recovery_codes: List[str]


class RoleInfo(BaseModel):
    role: str
    user_type: str
    cross_tenant: bool
    description: str


class RolesResponse(BaseModel):
    roles: List[RoleInfo]
