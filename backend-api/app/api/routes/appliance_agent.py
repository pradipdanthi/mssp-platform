"""
KB-016: Appliance Registration and Heartbeat Receiver Foundation.

New endpoints (appliance-facing only - no human platform_users caller ever
uses these, and no /admin/* or /customer/* endpoint is touched here):

- POST /appliance/register   - redeem a one-time activation token (created
                                via KB-015's admin API) and create the
                                appliance's own durable identity/credential
- POST /appliance/heartbeat  - accept a periodic health/status update from
                                an already-registered appliance

Authentication model (deliberately different from every other router in
this codebase - see app/api/dependencies.py for the human JWT/RBAC
equivalent, which is NOT used anywhere in this file):

- POST /appliance/register is authenticated by possession of a valid,
  unexpired, still-"pending" one-time activation_token in the request
  body. There is no appliance identity yet at this point, so there is
  nothing to check via headers.
- POST /appliance/heartbeat is authenticated by possession of a durable
  appliance API key, presented via the X-Appliance-ID/X-Appliance-API-Key
  headers and verified in app/services/appliance_auth_service.py.
- Neither endpoint accepts, checks, or requires a JWT. Neither endpoint
  uses Depends(get_current_user)/Depends(require_roles(...)).

Race-condition safety for activation-token redemption: the token row is
selected with `SELECT ... FOR UPDATE` inside a single transaction (see
app/db/session.py's db_transaction()), which serializes concurrent
redemption attempts against the same token - a second concurrent request
blocks until the first transaction commits or rolls back, then sees the
now-"used" status and is rejected at the very first check, before ever
attempting an INSERT. The appliance row is created BEFORE the token is
marked "used" (and consumption uses a belt-and-suspenders
compare-and-swap, `UPDATE ... WHERE status = 'pending'`), so a failed
appliance INSERT (e.g. a duplicate appliance_uuid) never wastes the
caller's token - it can be retried with the same still-pending token.

Security notes:

- The raw activation_token and raw appliance_api_key are never logged and
  never stored - only their SHA-256 hashes. See
  app/services/appliance_auth_service.py for the hashing/verification
  helpers.
- Every activation-token failure (not found, wrong status, expired) is
  reported identically as a generic 401 - this deliberately does not tell
  an unauthenticated caller *why* a token failed, to avoid letting a
  probing caller enumerate which tokens exist or their current status.
- Duplicate appliance_uuid/appliance_name conflicts are reported as a
  clean 409 - never a raw psycopg/UniqueViolation error.
- Unexpected internal failures are reported as a generic 500 with no
  database error text - full detail goes to server-side logs only.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request, status
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from app.db.session import db_transaction, fetch_one
from app.schemas.appliance_agent import (
    ApplianceHeartbeatRequest,
    ApplianceHeartbeatResponse,
    ApplianceRegisterRequest,
    ApplianceRegisterResponse,
)
from app.services.appliance_auth_service import (
    ApplianceRetiredError,
    InvalidApplianceCredentialsError,
    generate_appliance_api_key,
    hash_secret_sha256,
    verify_appliance_credentials,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/appliance", tags=["appliance-agent"])


class InvalidActivationTokenError(Exception):
    """Token not found, not pending, or expired. Always -> generic 401."""


class ActivationTokenConflictError(Exception):
    """
    Belt-and-suspenders case: the final compare-and-swap UPDATE affected
    zero rows even though the earlier SELECT ... FOR UPDATE saw status =
    'pending'. Should not normally happen given the row lock, but if it
    does, the whole transaction (including the just-inserted appliance
    row) is rolled back by db_transaction() -> reported as 409.
    """


class DuplicateApplianceError(Exception):
    """Wraps a UniqueViolation on appliances.appliance_uuid or the
    (tenant_id, appliance_name) constraint -> reported as 409."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _duplicate_conflict_message(exc: UniqueViolation) -> str:
    constraint = getattr(getattr(exc, "diag", None), "constraint_name", None) or ""
    if "appliance_uuid" in constraint:
        return "An appliance with this appliance_uuid already exists"
    if "appliance_name" in constraint:
        return "An appliance with this appliance_name already exists for this tenant"
    if "appliance_api_key_hash" in constraint:
        return "Appliance API key generation failed, please retry"
    return "A conflicting appliance record already exists"


@router.post(
    "/register",
    response_model=ApplianceRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_appliance(payload: ApplianceRegisterRequest) -> Dict[str, Any]:
    token_hash = hash_secret_sha256(payload.activation_token)
    appliance_uuid = payload.appliance_uuid or str(uuid4())
    raw_api_key, api_key_hash, api_key_hint = generate_appliance_api_key()
    local_ip_text = str(payload.local_ip) if payload.local_ip is not None else None
    health_snapshot = Jsonb(payload.health_snapshot) if payload.health_snapshot is not None else Jsonb({})

    try:
        with db_transaction() as cur:
            cur.execute(
                """
                SELECT id::text, tenant_id::text, site_name, status, expires_at
                FROM appliance_activation_tokens
                WHERE token_hash = %s
                FOR UPDATE;
                """,
                (token_hash,),
            )
            token_row = cur.fetchone()

            if not token_row:
                raise InvalidActivationTokenError()
            if token_row["status"] != "pending":
                raise InvalidActivationTokenError()
            if token_row["expires_at"] is not None and token_row["expires_at"] < datetime.now(timezone.utc):
                raise InvalidActivationTokenError()

            try:
                cur.execute(
                    """
                    INSERT INTO appliances (
                        tenant_id, activation_token_id, appliance_name, site_name,
                        appliance_uuid, agent_version, config_version, local_ip,
                        health_snapshot, status, appliance_api_key_hash,
                        appliance_api_key_hint, appliance_key_created_at
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s::inet,
                        %s, 'registered', %s,
                        %s, now()
                    )
                    RETURNING id::text, tenant_id::text, appliance_uuid, appliance_name,
                              site_name, status;
                    """,
                    (
                        token_row["tenant_id"],
                        token_row["id"],
                        payload.appliance_name,
                        token_row["site_name"],
                        appliance_uuid,
                        payload.agent_version,
                        payload.config_version,
                        local_ip_text,
                        health_snapshot,
                        api_key_hash,
                        api_key_hint,
                    ),
                )
            except UniqueViolation as exc:
                raise DuplicateApplianceError(_duplicate_conflict_message(exc)) from exc

            appliance_row = cur.fetchone()

            cur.execute(
                """
                UPDATE appliance_activation_tokens
                SET status = 'used', used_at = now()
                WHERE id = %s AND status = 'pending'
                RETURNING id;
                """,
                (token_row["id"],),
            )
            if not cur.fetchone():
                raise ActivationTokenConflictError()
    except InvalidActivationTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unusable activation token",
        )
    except ActivationTokenConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Activation token was already used, please request a new one",
        )
    except DuplicateApplianceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error during appliance registration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Appliance registration failed due to an internal error",
        )

    tenant = fetch_one("SELECT short_code FROM tenants WHERE id = %s;", (appliance_row["tenant_id"],))
    tenant_short_code = tenant.get("short_code") if tenant else None
    if not tenant_short_code:
        logger.error("Appliance %s registered but tenant %s could not be resolved", appliance_row["id"], appliance_row["tenant_id"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Appliance registration failed due to an internal error",
        )

    return {
        "appliance_id": appliance_row["id"],
        "appliance_uuid": appliance_row["appliance_uuid"],
        "tenant_id": appliance_row["tenant_id"],
        "tenant_short_code": tenant_short_code,
        "appliance_name": appliance_row["appliance_name"],
        "site_name": appliance_row["site_name"],
        "status": appliance_row["status"],
        "appliance_api_key": raw_api_key,
        "api_key_hint": api_key_hint,
        "message": "Appliance registered successfully. Store the appliance_api_key securely - it will not be shown again.",
    }


@router.post("/heartbeat", response_model=ApplianceHeartbeatResponse)
def appliance_heartbeat(
    payload: ApplianceHeartbeatRequest,
    request: Request,
    x_appliance_id: Optional[str] = Header(default=None, alias="X-Appliance-ID"),
    x_appliance_api_key: Optional[str] = Header(default=None, alias="X-Appliance-API-Key"),
) -> Dict[str, Any]:
    if not x_appliance_id or not x_appliance_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing appliance credentials",
        )

    try:
        appliance_id = str(UUID(x_appliance_id))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid appliance credentials",
        )

    try:
        appliance = verify_appliance_credentials(appliance_id, x_appliance_api_key)
    except InvalidApplianceCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid appliance credentials",
        )
    except ApplianceRetiredError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Appliance is retired and cannot send heartbeats",
        )

    source_ip = request.client.host if request.client else None
    local_ip_text = str(payload.local_ip) if payload.local_ip is not None else None
    health_status = payload.health_status or "unknown"
    health_snapshot = Jsonb(payload.health_snapshot) if payload.health_snapshot is not None else None

    try:
        with db_transaction() as cur:
            cur.execute(
                """
                INSERT INTO appliance_heartbeats (
                    appliance_id, source_ip, agent_version, health_status,
                    cpu_percent, memory_percent, disk_percent, details
                )
                VALUES (%s, %s::inet, %s, %s, %s, %s, %s, COALESCE(%s, '{}'::jsonb))
                RETURNING heartbeat_at::text;
                """,
                (
                    appliance["id"],
                    source_ip,
                    payload.agent_version,
                    health_status,
                    payload.cpu_percent,
                    payload.memory_percent,
                    payload.disk_percent,
                    health_snapshot,
                ),
            )
            heartbeat_row = cur.fetchone()

            cur.execute(
                """
                UPDATE appliances
                SET last_seen_at = now(),
                    last_source_ip = %s::inet,
                    appliance_key_last_used_at = now(),
                    local_ip = COALESCE(%s::inet, local_ip),
                    agent_version = COALESCE(%s, agent_version),
                    config_version = COALESCE(%s, config_version),
                    git_commit = COALESCE(%s, git_commit),
                    update_status = COALESCE(%s, update_status),
                    health_snapshot = COALESCE(%s, health_snapshot),
                    status = CASE WHEN status = 'maintenance' THEN status ELSE 'online' END
                WHERE id = %s
                RETURNING id::text, status;
                """,
                (
                    source_ip,
                    local_ip_text,
                    payload.agent_version,
                    payload.config_version,
                    payload.git_commit,
                    payload.update_status,
                    health_snapshot,
                    appliance["id"],
                ),
            )
            appliance_row = cur.fetchone()
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error while recording appliance heartbeat")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Heartbeat could not be recorded due to an internal error",
        )

    if not appliance_row:
        logger.error("Heartbeat inserted but appliance %s update returned no row", appliance["id"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Heartbeat could not be recorded due to an internal error",
        )

    return {
        "appliance_id": appliance_row["id"],
        "status": appliance_row["status"],
        "heartbeat_at": heartbeat_row["heartbeat_at"],
        "message": "Heartbeat received",
    }
