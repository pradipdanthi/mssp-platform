"""
KB-015: Admin Appliance Management API Foundation.

New endpoints (admin-side only - no appliance self-registration, activation
redemption, or heartbeat receiver here; that agent-facing surface is
deferred to KB-016 because it needs a fundamentally different, non-JWT
caller/authentication model):

- GET   /admin/appliances/{appliance_id}                                    - single appliance detail
- PATCH /admin/appliances/{appliance_id}                                    - update appliance_name/site_name/status only
- POST  /admin/tenants/{tenant_id}/appliance-activation-tokens              - create an activation token for a tenant
- GET   /admin/tenants/{tenant_id}/appliance-activation-tokens             - list a tenant's activation-token metadata
- PATCH /admin/appliance-activation-tokens/{token_id}/revoke               - revoke a still-pending token

These three URL namespaces are why this router uses no shared prefix -
APIRouter(tags=["admin-appliances"]) with each route given its own full
path string - rather than the single-prefix pattern used by
tenant_management.py/user_management.py.

RBAC: read access (GET appliance detail, GET token list) uses
ADMIN_SOC_ROLES imported from admin.py - platform_admin, soc_manager, and
soc_analyst. Write access (appliance PATCH, token create, token revoke) is
restricted to ADMIN_APPLIANCE_WRITE_ROLES = ("platform_admin",) only.
Customer roles get 403 on every endpoint here, same as every other
/admin/* endpoint; missing/invalid token gets 401.

There is intentionally no DELETE endpoint for either appliances or
activation tokens:
- appliance_heartbeats.appliance_id is ON DELETE CASCADE - a hard delete
  would permanently destroy an appliance's entire heartbeat/health
  history. protected_assets.appliance_id is ON DELETE SET NULL - a hard
  delete would silently orphan any assets tied to it. PATCH
  {"status": "retired"} achieves the same practical outcome reversibly.
- appliance_activation_tokens.created_by_user_id exists specifically to
  attribute who issued a token; revoke already covers "make this token
  unusable" without destroying that audit trail.

There is also no way to manually set an activation token's status to
"expired" - expiry is a consequence of comparing expires_at to the current
time, not a discrete admin action the way revoke is, and there is no
scheduled worker in this codebase to flip it automatically. Whatever
eventually redeems a token (KB-016) should check expires_at itself at
redemption time regardless of the stored status value.

appliance_id/tenant_id/token_id are UUID path parameters, validated by
FastAPI/Pydantic before any query runs - an invalid UUID never produces a
raw database error, only a clean 422.

KB-017 addition: two credential-focused endpoints on top of the KB-015
appliance/token endpoints above -

- GET  /admin/appliances/{appliance_id}/credential          - safe credential metadata only
- POST /admin/appliances/{appliance_id}/credential/rotate   - rotate/reissue the durable appliance API key

These are deliberately separate from GET/PATCH
/admin/appliances/{appliance_id} rather than folded into ApplianceDetail -
the existing, already-validated KB-015 appliance detail response shape is
left completely untouched. Read access reuses ADMIN_SOC_ROLES (same as
appliance detail/token list); rotation uses its own, more restrictive
ADMIN_APPLIANCE_CREDENTIAL_WRITE_ROLES = ("platform_admin",) rather than
reusing ADMIN_APPLIANCE_WRITE_ROLES, so credential issuance permissions can
diverge from general appliance-metadata write permissions in the future
without a rename. Rotation is intentionally allowed even for a retired
appliance and even when no credential has ever been issued (recovery /
recommissioning), and never changes appliance status - it only ever
touches the four appliance_api_key_* columns.
"""

import hashlib
import secrets
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field, field_validator
import ipaddress

from app.api.dependencies import require_roles
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_all, fetch_one, fetch_one_write
from app.schemas.appliances import (
    ActivationTokenCreateRequest,
    ActivationTokenCreateResponse,
    ActivationTokenMetadata,
    ActivationTokensListResponse,
    ApplianceCredentialMetadata,
    ApplianceCredentialRotateResponse,
    ApplianceDetail,
    ApplianceUpdateRequest,
)
from app.services.appliance_auth_service import generate_appliance_api_key
from app.services import appliance_jobs as appliance_jobs_service


class ApplianceAgentCidrsRequest(BaseModel):
    """Admin-set LAN CIDRs allowed to reach this appliance's local Manager."""

    cidrs: List[str] = Field(default_factory=list, max_length=64)

    @field_validator("cidrs")
    @classmethod
    def validate_cidrs(cls, values: List[str]) -> List[str]:
        cleaned: List[str] = []
        for raw in values:
            s = str(raw).strip()
            if not s:
                continue
            try:
                net = ipaddress.ip_network(s, strict=False)
            except ValueError as exc:
                raise ValueError(f"invalid CIDR '{s}': {exc}") from exc
            if net.version != 4:
                raise ValueError(f"only IPv4 CIDRs supported: {s}")
            cleaned.append(str(net))
        # de-dupe
        seen = set()
        out: List[str] = []
        for c in cleaned:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out


class ApplianceAgentCidrsResponse(BaseModel):
    appliance_id: str
    agent_source_cidrs: List[str]
    job_id: Optional[str] = None
    message: str


router = APIRouter(tags=["admin-appliances"])

# KB-015: only platform_admin may update appliance metadata/status, create
# activation tokens, or revoke activation tokens. soc_manager and
# soc_analyst keep read-only access (ADMIN_SOC_ROLES, imported from
# admin.py), same read tier as tenant/user management.
ADMIN_APPLIANCE_WRITE_ROLES = ("platform_admin",)

# KB-017: credential rotation gets its own write-role constant, kept
# distinct from ADMIN_APPLIANCE_WRITE_ROLES above even though the value is
# identical today, so issuing a fresh appliance credential can be
# permissioned separately from general appliance-metadata writes later
# without renaming anything.
ADMIN_APPLIANCE_CREDENTIAL_WRITE_ROLES = ("platform_admin",)

# secrets.token_urlsafe(32) yields 256 bits of cryptographically secure
# randomness (~43 URL-safe characters) - a fast, deterministic hash
# (SHA-256) is the correct tool for storing/verifying a high-entropy
# random token like this, unlike bcrypt, which is designed to slow down
# brute-forcing a low-entropy, human-chosen secret such as a password.
RAW_TOKEN_BYTES = 32
TOKEN_HINT_LENGTH = 6

_APPLIANCE_DETAIL_QUERY = """
    SELECT
        a.id::text,
        a.tenant_id::text,
        t.name AS tenant_name,
        t.short_code AS tenant_short_code,
        t.deployment_mode,
        a.appliance_name,
        a.site_name,
        a.status,
        a.agent_version,
        a.config_version,
        a.update_status,
        a.local_ip::text,
        a.last_source_ip::text,
        a.last_seen_at::text,
        a.created_at::text,
        a.updated_at::text,
        COALESCE(a.enabled_services, '{}'::text[]) AS enabled_services,
        COALESCE(a.agent_source_cidrs, '{}'::text[]) AS agent_source_cidrs,
        count(DISTINCT pa.id) AS protected_assets,
        h.health_status AS latest_health_status,
        h.heartbeat_at::text AS latest_heartbeat_at
    FROM appliances a
    JOIN tenants t ON t.id = a.tenant_id
    LEFT JOIN protected_assets pa ON pa.appliance_id = a.id
    LEFT JOIN LATERAL (
        SELECT health_status, heartbeat_at
        FROM appliance_heartbeats hb
        WHERE hb.appliance_id = a.id
        ORDER BY hb.heartbeat_at DESC
        LIMIT 1
    ) h ON true
    WHERE a.id = %s
    GROUP BY a.id, t.name, t.short_code, t.deployment_mode, h.health_status, h.heartbeat_at;
"""

_TOKEN_METADATA_COLUMNS = """
    id::text,
    tenant_id::text,
    site_name,
    token_hint,
    status,
    expires_at::text,
    used_at::text,
    created_by_user_id::text,
    created_at::text
"""

# KB-017: appliance_api_key_hash is deliberately never selected here - only
# a boolean derived from it (has_appliance_api_key). No query in this file
# ever puts the raw hash column into a result row that a response model
# could accidentally expose.
_APPLIANCE_CREDENTIAL_QUERY = """
    SELECT
        id::text AS appliance_id,
        (appliance_api_key_hash IS NOT NULL) AS has_appliance_api_key,
        appliance_api_key_hint,
        appliance_key_created_at::text,
        appliance_key_last_used_at::text,
        status,
        last_seen_at::text
    FROM appliances
    WHERE id = %s;
"""


def _fetch_appliance_detail(appliance_id: UUID) -> Optional[Dict[str, Any]]:
    row = fetch_one(_APPLIANCE_DETAIL_QUERY, (str(appliance_id),))
    return row or None


def _fetch_token_metadata(token_id: UUID) -> Optional[Dict[str, Any]]:
    row = fetch_one(
        f"SELECT {_TOKEN_METADATA_COLUMNS} FROM appliance_activation_tokens WHERE id = %s;",
        (str(token_id),),
    )
    return row or None


def _generate_activation_token() -> "tuple[str, str, str]":
    raw_token = secrets.token_urlsafe(RAW_TOKEN_BYTES)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    token_hint = raw_token[-TOKEN_HINT_LENGTH:]
    return raw_token, token_hash, token_hint


@router.get("/admin/appliances/{appliance_id}", response_model=ApplianceDetail)
def get_appliance_detail(
    appliance_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    appliance = _fetch_appliance_detail(appliance_id)
    if not appliance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appliance not found")
    return appliance


@router.put(
    "/admin/appliances/{appliance_id}/agent-source-cidrs",
    response_model=ApplianceAgentCidrsResponse,
)
def put_appliance_agent_source_cidrs(
    appliance_id: UUID,
    payload: ApplianceAgentCidrsRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_APPLIANCE_WRITE_ROLES)),
) -> Dict[str, Any]:
    """
    Set multi-subnet agent allow-list for an appliance and enqueue a job so the
    online appliance applies nftables (ports 1514/1515) on next heartbeat.
    """
    appliance = fetch_one(
        """
        SELECT id::text, tenant_id::text, status
        FROM appliances
        WHERE id = %s::uuid;
        """,
        (str(appliance_id),),
    )
    if not appliance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appliance not found")

    updated = fetch_one_write(
        """
        UPDATE appliances
        SET agent_source_cidrs = %s::text[],
            updated_at = NOW()
        WHERE id = %s::uuid
        RETURNING id::text, COALESCE(agent_source_cidrs, '{}'::text[]) AS agent_source_cidrs;
        """,
        (payload.cidrs, str(appliance_id)),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appliance not found")

    job = appliance_jobs_service.enqueue_job(
        appliance_id=appliance["id"],
        tenant_id=appliance["tenant_id"],
        job_type="set_agent_cidrs",
        payload={"cidrs": list(payload.cidrs)},
        requested_by_user_id=str(current_user.get("id") or "") or None,
    )
    return {
        "appliance_id": updated["id"],
        "agent_source_cidrs": list(updated.get("agent_source_cidrs") or []),
        "job_id": job.get("id"),
        "message": (
            "CIDRs saved. Appliance will apply firewall allow-list on next heartbeat "
            "(usually within ~60s if online)."
        ),
    }


@router.post("/admin/appliances/{appliance_id}/channel/enqueue")
def admin_enqueue_channel_frame(
    appliance_id: UUID,
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_APPLIANCE_WRITE_ROLES)),
) -> Dict[str, Any]:
    """Push ota.offer / license.push / control / job frame to appliance channel inbox."""
    from app.services import appliance_channel as channel_service

    appliance = fetch_one(
        "SELECT id::text, tenant_id::text, status FROM appliances WHERE id = %s::uuid;",
        (str(appliance_id),),
    )
    if not appliance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appliance not found")
    frame_type = str(payload.get("frame_type") or "").strip()
    if frame_type not in ("ota.offer", "license.push", "control", "job"):
        raise HTTPException(status_code=400, detail="frame_type must be ota.offer|license.push|control|job")
    row = channel_service.enqueue_frame(
        appliance_id=appliance["id"],
        tenant_id=appliance["tenant_id"],
        frame_type=frame_type,
        payload=payload.get("payload") or {},
    )
    return {"ok": True, "frame": row}

@router.patch("/admin/appliances/{appliance_id}", response_model=ApplianceDetail)
def update_appliance(
    appliance_id: UUID,
    payload: ApplianceUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_APPLIANCE_WRITE_ROLES)),
) -> Dict[str, Any]:
    fields = []
    params: list = []

    # KB-015 scope only: appliance_name, site_name, status. No
    # agent-reported fields - see module docstring.
    for field_name in ("appliance_name", "site_name", "status"):
        value = getattr(payload, field_name)
        if value is not None:
            fields.append(f"{field_name} = %s")
            params.append(value)

    if not fields:
        # Guarded already by ApplianceUpdateRequest's model_validator, kept
        # here too as defense in depth.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one field must be provided")

    params.append(str(appliance_id))
    query = f"UPDATE appliances SET {', '.join(fields)} WHERE id = %s RETURNING id::text;"

    try:
        updated = fetch_one_write(query, tuple(params))
    except UniqueViolation:
        # appliances has UNIQUE (tenant_id, appliance_name) - renaming an
        # appliance to a name already used by another appliance in the
        # same tenant hits this constraint.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An appliance with this appliance_name already exists for this tenant",
        )

    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appliance not found")

    appliance = _fetch_appliance_detail(UUID(updated["id"]))
    if not appliance:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Appliance update failed")
    return appliance


@router.post(
    "/admin/tenants/{tenant_id}/appliance-activation-tokens",
    response_model=ActivationTokenCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_activation_token(
    tenant_id: UUID,
    payload: ActivationTokenCreateRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_APPLIANCE_WRITE_ROLES)),
) -> Dict[str, Any]:
    tenant_exists = fetch_one("SELECT id FROM tenants WHERE id = %s;", (str(tenant_id),))
    if not tenant_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    raw_token, token_hash, token_hint = _generate_activation_token()

    try:
        created = fetch_one_write(
            """
            INSERT INTO appliance_activation_tokens
                (tenant_id, site_name, token_hash, token_hint, status, expires_at, created_by_user_id)
            VALUES (%s, %s, %s, %s, 'pending', now() + (%s * interval '1 hour'), %s)
            RETURNING id::text;
            """,
            (
                str(tenant_id),
                payload.site_name,
                token_hash,
                token_hint,
                payload.expires_in_hours,
                current_user["id"],
            ),
        )
    except UniqueViolation:
        # token_hash is UNIQUE. With 256 bits of secrets.token_urlsafe()
        # randomness a real collision is not realistically expected - this
        # is a defensive backstop only, never a normal-path outcome.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Activation token generation failed, please retry",
        )

    token = _fetch_token_metadata(UUID(created["id"]))
    if not token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Activation token creation failed")

    return {"token": raw_token, "metadata": token}


@router.get(
    "/admin/tenants/{tenant_id}/appliance-activation-tokens",
    response_model=ActivationTokensListResponse,
)
def list_activation_tokens(
    tenant_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, List[Dict[str, Any]]]:
    tenant_exists = fetch_one("SELECT id FROM tenants WHERE id = %s;", (str(tenant_id),))
    if not tenant_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    rows = fetch_all(
        f"""
        SELECT {_TOKEN_METADATA_COLUMNS}
        FROM appliance_activation_tokens
        WHERE tenant_id = %s
        ORDER BY created_at DESC;
        """,
        (str(tenant_id),),
    )
    return {"tokens": rows}


@router.patch(
    "/admin/appliance-activation-tokens/{token_id}/revoke",
    response_model=ActivationTokenMetadata,
)
def revoke_activation_token(
    token_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_APPLIANCE_WRITE_ROLES)),
) -> Dict[str, Any]:
    existing = fetch_one(
        "SELECT id::text, status FROM appliance_activation_tokens WHERE id = %s;",
        (str(token_id),),
    )
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activation token not found")

    if existing["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Activation token cannot be revoked because its status is '{existing['status']}'",
        )

    updated = fetch_one_write(
        """
        UPDATE appliance_activation_tokens
        SET status = 'revoked'
        WHERE id = %s AND status = 'pending'
        RETURNING id::text;
        """,
        (str(token_id),),
    )
    if not updated:
        # Race-condition backstop: status changed between the check above
        # and this UPDATE (e.g. two concurrent revoke requests).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Activation token status changed - please retry",
        )

    token = _fetch_token_metadata(UUID(updated["id"]))
    if not token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Activation token revoke failed")
    return token


@router.get(
    "/admin/appliances/{appliance_id}/credential",
    response_model=ApplianceCredentialMetadata,
)
def get_appliance_credential(
    appliance_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    credential = fetch_one(_APPLIANCE_CREDENTIAL_QUERY, (str(appliance_id),))
    if not credential:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appliance not found")
    return credential


@router.post(
    "/admin/appliances/{appliance_id}/credential/rotate",
    response_model=ApplianceCredentialRotateResponse,
)
def rotate_appliance_credential(
    appliance_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_APPLIANCE_CREDENTIAL_WRITE_ROLES)),
) -> Dict[str, Any]:
    # KB-016's generate_appliance_api_key() reused unchanged: (raw_key,
    # key_hash, key_hint). raw_key is only ever placed in this function's
    # return value below - never stored, never logged.
    raw_key, key_hash, key_hint = generate_appliance_api_key()

    try:
        rotated = fetch_one_write(
            """
            UPDATE appliances
            SET appliance_api_key_hash = %s,
                appliance_api_key_hint = %s,
                appliance_key_created_at = now(),
                appliance_key_last_used_at = NULL
            WHERE id = %s
            RETURNING id::text, appliance_key_created_at::text;
            """,
            (key_hash, key_hint, str(appliance_id)),
        )
    except UniqueViolation:
        # appliance_api_key_hash is UNIQUE. With 256 bits of
        # secrets.token_urlsafe() randomness a real collision is not
        # realistically expected - this is a defensive backstop only,
        # never a normal-path outcome (same pattern already used for
        # activation token_hash collisions in create_activation_token
        # above).
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Credential rotation failed, please retry",
        )

    if not rotated:
        # Rotation is intentionally allowed regardless of appliance status
        # (including retired) and regardless of whether a credential was
        # ever previously issued - the only reason this UPDATE returns no
        # row is that appliance_id does not exist.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appliance not found")

    return {
        "appliance_id": rotated["id"],
        "appliance_api_key": raw_key,
        "api_key_hint": key_hint,
        "appliance_key_created_at": rotated["appliance_key_created_at"],
        "message": (
            "Appliance credential rotated successfully. The previous "
            "appliance_api_key is now invalid. Store this new "
            "appliance_api_key securely - it will not be shown again."
        ),
    }
