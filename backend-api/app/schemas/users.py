"""
KB-014: Request/response models for the /admin/users/* management
endpoints (list, get one, create, update, password set).

user_type is intentionally never an accepted input field anywhere in this
module - it is always derived server-side from role (see ADMIN_ROLES /
CUSTOMER_ROLES below and app/api/routes/user_management.py), so a
role/user_type mismatch is structurally impossible to submit, the same way
UserPublic in app/schemas/auth.py has no password field at all.
"""

from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

RoleLiteral = Literal["platform_admin", "soc_manager", "soc_analyst", "customer_admin", "customer_viewer"]
StatusLiteral = Literal["active", "inactive", "locked"]

# Single source of truth for which roles are admin/SOC (cross-tenant, must
# never carry a tenant_id) vs. customer (tenant-scoped, must always carry a
# valid tenant_id). Matches the platform_users_role_check constraint in
# postgres/init/002_kb010_auth_rbac.sql exactly.
ADMIN_ROLES = {"platform_admin", "soc_manager", "soc_analyst"}
CUSTOMER_ROLES = {"customer_admin", "customer_viewer"}

# Basic email shape check only (not full RFC 5322) - deliberately avoids
# adding pydantic's EmailStr / the email-validator dependency, since a
# simple pattern is enough for this foundation module and keeps
# requirements.txt untouched.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=EMAIL_PATTERN)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    role: RoleLiteral
    tenant_id: Optional[UUID] = None
    phone: Optional[str] = Field(default=None, max_length=40)
    status: StatusLiteral = "active"

    @model_validator(mode="after")
    def normalize_and_check_tenant(self) -> "UserCreateRequest":
        self.email = self.email.strip().lower()

        if self.role in ADMIN_ROLES and self.tenant_id is not None:
            raise ValueError("platform_admin/soc_manager/soc_analyst users must not have a tenant_id")
        if self.role in CUSTOMER_ROLES and self.tenant_id is None:
            raise ValueError("customer_admin/customer_viewer users must have a tenant_id")
        return self


class UserUpdateRequest(BaseModel):
    """
    KB-014 scope only: full_name, phone, status. No email, role, tenant_id,
    or user_type change - those are deferred to a future module (same
    treatment KB-013 gave to short_code).
    """

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=40)
    status: Optional[StatusLiteral] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UserUpdateRequest":
        if all(v is None for v in self.__dict__.values()):
            raise ValueError("At least one field must be provided")
        return self


class UserPasswordUpdateRequest(BaseModel):
    """Admin-triggered password set, not a self-service reset flow."""

    new_password: str = Field(min_length=8, max_length=128)


class UserDetail(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    user_type: str
    role: str
    full_name: str
    email: str
    phone: Optional[str] = None
    status: str
    last_login_at: Optional[str] = None
    created_at: str
    updated_at: str
    # No password / password_hash field - structurally impossible to leak.


class UsersListResponse(BaseModel):
    users: List[UserDetail]
