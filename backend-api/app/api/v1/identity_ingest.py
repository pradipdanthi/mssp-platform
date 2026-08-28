"""Phase 6: Okta & Active Directory identity telemetry ingest."""

from __future__ import annotations

import hmac
import logging
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.db.session import db_transaction, fetch_one
from app.services.appliance_auth_service import (
    ApplianceRetiredError,
    InvalidApplianceCredentialsError,
    verify_appliance_credentials,
)
from app.services.identity_threat_engine import (
    configured_identity_api_key,
    process_ad_event,
    process_okta_event,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/telemetry", tags=["identity-telemetry"])


class IdentityIngestResponse(BaseModel):
    accepted: bool = True
    tenant_id: str
    events_processed: int
    alerts_created: int
    alert_ids: List[str] = Field(default_factory=list)


class OktaTelemetryRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    events: Optional[List[Dict[str, Any]]] = None


class AdTelemetryRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    events: Optional[List[Dict[str, Any]]] = None


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _verify_agent_api_key(provided: Optional[str]) -> None:
    expected = configured_identity_api_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity telemetry ingest is not configured",
        )
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent API credentials",
        )


def _resolve_tenant_id(
    *,
    x_tenant_id: Optional[str],
    x_appliance_id: Optional[str],
    x_appliance_api_key: Optional[str],
    authorization: Optional[str],
    x_agent_api_key: Optional[str],
) -> str:
    """Authenticate agent/appliance and return scoped tenant_id."""
    if x_appliance_id and x_appliance_api_key:
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
                detail="Appliance is retired",
            )
        tenant_id = appliance.get("tenant_id")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Appliance is not bound to a tenant",
            )
        return str(tenant_id)

    api_key = (x_agent_api_key or _extract_bearer(authorization) or "").strip()
    _verify_agent_api_key(api_key or None)
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required for agent API key auth",
        )
    try:
        tenant_uuid = str(UUID(x_tenant_id))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Tenant-ID",
        )
    row = fetch_one("SELECT id::text FROM tenants WHERE id = %s::uuid;", (tenant_uuid,))
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return tenant_uuid


def _normalize_events(
    payload: Union[Dict[str, Any], BaseModel],
    list_key: str = "events",
) -> List[Dict[str, Any]]:
    if isinstance(payload, BaseModel):
        data: Dict[str, Any] = payload.model_dump()
    else:
        data = payload
    nested = data.get(list_key)
    if isinstance(nested, list) and nested:
        return [e for e in nested if isinstance(e, dict)]
    if data.get("eventType") or data.get("EventID") or data.get("event_id"):
        return [data]
    return []


@router.post("/okta", response_model=IdentityIngestResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_okta_telemetry(
    payload: OktaTelemetryRequest,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_agent_api_key: Optional[str] = Header(default=None, alias="X-Agent-API-Key"),
    x_appliance_id: Optional[str] = Header(default=None, alias="X-Appliance-ID"),
    x_appliance_api_key: Optional[str] = Header(default=None, alias="X-Appliance-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> IdentityIngestResponse:
    """Accept Okta System Log JSON (e.g. MFA, session start)."""
    tenant_id = _resolve_tenant_id(
        x_tenant_id=x_tenant_id,
        x_appliance_id=x_appliance_id,
        x_appliance_api_key=x_appliance_api_key,
        authorization=authorization,
        x_agent_api_key=x_agent_api_key,
    )
    events = _normalize_events(payload)
    if not events:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No Okta events supplied",
        )

    alert_ids: List[str] = []
    with db_transaction() as cur:
        for event in events:
            alert_ids.extend(process_okta_event(tenant_id, event, cur=cur))

    logger.info(
        "okta telemetry ingested tenant=%s events=%s alerts=%s",
        tenant_id,
        len(events),
        len(alert_ids),
    )
    return IdentityIngestResponse(
        tenant_id=tenant_id,
        events_processed=len(events),
        alerts_created=len(alert_ids),
        alert_ids=alert_ids,
    )


@router.post("/ad", response_model=IdentityIngestResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_ad_telemetry(
    payload: AdTelemetryRequest,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_agent_api_key: Optional[str] = Header(default=None, alias="X-Agent-API-Key"),
    x_appliance_id: Optional[str] = Header(default=None, alias="X-Appliance-ID"),
    x_appliance_api_key: Optional[str] = Header(default=None, alias="X-Appliance-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> IdentityIngestResponse:
    """Accept Windows security events (4624/4625/4768/4769)."""
    tenant_id = _resolve_tenant_id(
        x_tenant_id=x_tenant_id,
        x_appliance_id=x_appliance_id,
        x_appliance_api_key=x_appliance_api_key,
        authorization=authorization,
        x_agent_api_key=x_agent_api_key,
    )
    events = _normalize_events(payload)
    if not events:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No Active Directory events supplied",
        )

    allowed = {4624, 4625, 4768, 4769}
    filtered = [e for e in events if _ad_event_allowed(e, allowed)]
    if not filtered:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No supported AD event IDs (4624, 4625, 4768, 4769)",
        )

    alert_ids: List[str] = []
    with db_transaction() as cur:
        for event in filtered:
            alert_ids.extend(process_ad_event(tenant_id, event, cur=cur))

    logger.info(
        "ad telemetry ingested tenant=%s events=%s alerts=%s",
        tenant_id,
        len(filtered),
        len(alert_ids),
    )
    return IdentityIngestResponse(
        tenant_id=tenant_id,
        events_processed=len(filtered),
        alerts_created=len(alert_ids),
        alert_ids=alert_ids,
    )


def _ad_event_allowed(event: Dict[str, Any], allowed: set) -> bool:
    for key in ("EventID", "event_id", "eventId"):
        if key in event:
            try:
                return int(event[key]) in allowed
            except (TypeError, ValueError):
                continue
    system = event.get("System") or event.get("system")
    if isinstance(system, dict):
        for key in ("EventID", "EventId"):
            if key in system:
                try:
                    return int(system[key]) in allowed
                except (TypeError, ValueError):
                    continue
    return False
