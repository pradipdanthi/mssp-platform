"""
KB-010: Request/response models for the /auth/* endpoints.

UserPublic intentionally has no password/hash field at all - it is
structurally impossible for a password hash to leak through this model,
because the field simply does not exist on it.
"""

from typing import List, Literal, Optional

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
    status: str
    last_login_at: Optional[str] = None
    # KB-034: optional contact phone; never a secret.
    phone: Optional[str] = None


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


class RoleInfo(BaseModel):
    role: str
    user_type: str
    cross_tenant: bool
    description: str


class RolesResponse(BaseModel):
    roles: List[RoleInfo]
