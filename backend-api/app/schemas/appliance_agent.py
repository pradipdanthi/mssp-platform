"""
KB-016: Request/response models for the appliance-facing registration and
heartbeat endpoints (POST /appliance/register, POST /appliance/heartbeat).

Design notes:

- These models are used by unauthenticated-until-proven-otherwise appliance
  callers, not by human platform_users - there is no request model here
  that carries a JWT, and no response model here is reused by any
  /admin/* or /customer/* endpoint.

- ApplianceRegisterRequest and ApplianceHeartbeatRequest both set
  `model_config = ConfigDict(extra="forbid")`. This is a deliberate,
  security-motivated choice specific to this module: an appliance caller
  must never be able to smuggle in tenant_id, site_name,
  appliance_api_key, token_hash, or appliance_api_key_hash by simply
  including them in the request body - "forbid" turns any such attempt
  into a clean 422 instead of Pydantic's default "silently ignore unknown
  fields" behavior, which would otherwise hide the fact that the field
  was rejected.

- local_ip uses Pydantic's IPvAnyAddress so a malformed IP address is
  caught as a clean 422 before it ever reaches PostgreSQL's INET column -
  never a raw database error.

- ApplianceRegisterResponse.appliance_api_key is the ONLY place the raw,
  durable appliance API key is ever returned - once, at registration.
  ApplianceHeartbeatResponse (and every other model in this file) has no
  field capable of carrying a raw key or any hash - structurally
  impossible to leak, the same principle ActivationTokenMetadata in
  app/schemas/appliances.py already uses for token_hash.
"""

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress

HealthStatusLiteral = Literal["healthy", "warning", "critical", "unknown"]
UpdateStatusLiteral = Literal["unknown", "current", "update_available", "updating", "failed"]


class ApplianceRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Sensitive: redacted by app/core/error_handlers.py on any 422 for this
    # field (SENSITIVE_KEYS includes "activation_token" - see KB-016
    # extension there). Never logged, never echoed back.
    activation_token: str = Field(min_length=16, max_length=512)

    appliance_name: str = Field(min_length=1, max_length=200)
    appliance_uuid: Optional[str] = Field(default=None, min_length=1, max_length=200)
    agent_version: Optional[str] = Field(default=None, max_length=100)
    config_version: Optional[str] = Field(default=None, max_length=100)
    local_ip: Optional[IPvAnyAddress] = None
    health_snapshot: Optional[Dict[str, Any]] = None

    # Deliberately absent: tenant_id, site_name (both come from the
    # activation token only - see Decision B), appliance_api_key,
    # token_hash, appliance_api_key_hash. extra="forbid" above rejects any
    # of these with a clean 422 rather than silently ignoring them.


class ApplianceRegisterResponse(BaseModel):
    appliance_id: str
    appliance_uuid: str
    tenant_id: str
    tenant_short_code: str
    appliance_name: str
    site_name: str
    status: str
    # One-time only - never stored, never returned by any other endpoint.
    appliance_api_key: str
    api_key_hint: str
    message: str


class ApplianceHeartbeatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    health_status: Optional[HealthStatusLiteral] = None
    agent_version: Optional[str] = Field(default=None, max_length=100)
    config_version: Optional[str] = Field(default=None, max_length=100)
    git_commit: Optional[str] = Field(default=None, max_length=100)
    update_status: Optional[UpdateStatusLiteral] = None
    local_ip: Optional[IPvAnyAddress] = None
    health_snapshot: Optional[Dict[str, Any]] = None
    cpu_percent: Optional[float] = Field(default=None, ge=0, le=100)
    memory_percent: Optional[float] = Field(default=None, ge=0, le=100)
    disk_percent: Optional[float] = Field(default=None, ge=0, le=100)

    # Deliberately absent: appliance_api_key, appliance_api_key_hash,
    # token_hash, activation_token, tenant_id. Credentials for this
    # endpoint travel only in the X-Appliance-ID/X-Appliance-API-Key
    # headers, never in the body. extra="forbid" above rejects any of
    # these fields with a clean 422 rather than silently ignoring them.


class ApplianceHeartbeatResponse(BaseModel):
    appliance_id: str
    status: str
    heartbeat_at: str
    message: str
