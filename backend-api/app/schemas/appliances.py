"""
KB-015: Request/response models for the admin appliance management
endpoints (appliance detail/update, activation token create/list/revoke).

Design notes (see docs/KB015 planning discussion for the full rationale):

- ApplianceUpdateRequest deliberately excludes every agent-reported field
  (appliance_uuid, agent_version, config_version, git_commit,
  update_status, local_ip, last_source_ip, last_seen_at, health_snapshot).
  Those are written by the appliance's own heartbeat process (KB-016, not
  yet built) - letting an admin freely overwrite them would let the API
  lie about an appliance's real observed state. Only appliance_name,
  site_name, and status are safe, genuinely admin-owned metadata.

- ActivationTokenMetadata has no token_hash field and no raw-token field -
  structurally impossible to leak through this model, the same principle
  UserDetail in app/schemas/users.py uses for password_hash.

- ActivationTokenCreateResponse is the ONLY model in this file that ever
  carries the raw one-time token, and only at creation time. No other
  endpoint (list, revoke, or any future GET) returns a `token` field.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

ApplianceStatusLiteral = Literal["registered", "online", "offline", "maintenance", "retired"]
TokenStatusLiteral = Literal["pending", "used", "expired", "revoked"]


class ApplianceUpdateRequest(BaseModel):
    """
    KB-015 scope only: appliance_name, site_name, status. No agent-reported
    fields - see module docstring above.
    """

    appliance_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    site_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[ApplianceStatusLiteral] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ApplianceUpdateRequest":
        if all(v is None for v in self.__dict__.values()):
            raise ValueError("At least one field must be provided")
        return self


class ApplianceDetail(BaseModel):
    id: str
    tenant_id: str
    tenant_name: str
    tenant_short_code: str
    appliance_name: str
    site_name: str
    status: str
    agent_version: Optional[str] = None
    config_version: Optional[str] = None
    update_status: Optional[str] = None
    local_ip: Optional[str] = None
    last_source_ip: Optional[str] = None
    last_seen_at: Optional[str] = None
    created_at: str
    updated_at: str
    protected_assets: int
    latest_health_status: Optional[str] = None
    latest_heartbeat_at: Optional[str] = None
    # No health_snapshot (raw agent JSON blob) - not needed for admin
    # metadata management in this foundation module.


class ActivationTokenCreateRequest(BaseModel):
    site_name: str = Field(min_length=1, max_length=200)
    expires_in_hours: int = Field(default=24, ge=1, le=720)


class ActivationTokenMetadata(BaseModel):
    id: str
    tenant_id: str
    site_name: str
    token_hint: Optional[str] = None
    status: str
    expires_at: Optional[str] = None
    used_at: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_at: str
    # Deliberately no token_hash and no raw token field.


class ActivationTokenCreateResponse(BaseModel):
    token: str
    metadata: ActivationTokenMetadata


class ActivationTokensListResponse(BaseModel):
    tokens: List[ActivationTokenMetadata]
