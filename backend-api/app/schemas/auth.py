"""
KB-010: Request/response models for the /auth/* endpoints.

UserPublic intentionally has no password/hash field at all - it is
structurally impossible for a password hash to leak through this model,
because the field simply does not exist on it.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class UserPublic(BaseModel):
    id: str
    email: str
    full_name: str
    user_type: str
    role: str
    tenant_id: Optional[str] = None
    status: str
    last_login_at: Optional[str] = None


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
