"""KB-093E: appliance telemetry ingest at /api/v1/telemetry/* (Kevantic Edge contract).

Reuses KB-057 safe field set and appliance API-key auth. Production may move
this router to the separate Appliance Management plane.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.routes.appliance_alert_ingest import ingest_appliance_alert
from app.schemas.alert_ingest import ApplianceAlertIngestRequest
from app.services.appliance_auth_service import (
    ApplianceRetiredError,
    InvalidApplianceCredentialsError,
    verify_appliance_credentials,
)
from fastapi import Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry-ingest"])


class HuntHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Optional[str] = None
    ts: Optional[str] = None
    src_ip: Optional[str] = None
    dst_ip: Optional[str] = None
    domain_name: Optional[str] = None
    file_hash: Optional[str] = None
    cve: Optional[str] = None
    source_tool: Optional[str] = None
    external_id: Optional[str] = None
    matched_ioc: Optional[str] = None
    parquet_path: Optional[str] = None


class HuntResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=32)
    lookback_days: Optional[int] = None
    ioc_count: Optional[int] = None
    hit_count: Optional[int] = None
    hits: List[HuntHit] = Field(default_factory=list)
    completed_at: Optional[str] = None
    error: Optional[str] = None


def _auth_appliance(
    x_appliance_id: Optional[str],
    x_appliance_api_key: Optional[str],
) -> Dict[str, Any]:
    if not x_appliance_id or not x_appliance_api_key:
        raise HTTPException(status_code=401, detail="Missing appliance credentials")
    try:
        appliance_id = str(UUID(x_appliance_id))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid appliance credentials")
    try:
        return verify_appliance_credentials(appliance_id, x_appliance_api_key)
    except InvalidApplianceCredentialsError:
        raise HTTPException(status_code=401, detail="Invalid appliance credentials")
    except ApplianceRetiredError:
        raise HTTPException(status_code=403, detail="Appliance is retired")


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
def telemetry_ingest(
    payload: ApplianceAlertIngestRequest,
    response: Response,
    x_appliance_id: Optional[str] = Header(default=None, alias="X-Appliance-ID"),
    x_appliance_api_key: Optional[str] = Header(default=None, alias="X-Appliance-API-Key"),
) -> Dict[str, Any]:
    """Normalized anonymized alert from Kevantic Edge Appliance."""
    return ingest_appliance_alert(
        payload,
        response,
        x_appliance_id=x_appliance_id,
        x_appliance_api_key=x_appliance_api_key,
    )


@router.post("/hunt-results", status_code=status.HTTP_202_ACCEPTED)
def telemetry_hunt_results(
    payload: HuntResultRequest,
    x_appliance_id: Optional[str] = Header(default=None, alias="X-Appliance-ID"),
    x_appliance_api_key: Optional[str] = Header(default=None, alias="X-Appliance-API-Key"),
) -> Dict[str, Any]:
    """Accept retrospective hunt results from the appliance (metadata hits only)."""
    appliance = _auth_appliance(x_appliance_id, x_appliance_api_key)
    from app.services import retrospective_service as retro

    updated = retro.apply_hunt_result(
        payload.job_id,
        status=payload.status,
        hits=[h.model_dump() for h in (payload.hits or [])],
        hit_count=payload.hit_count,
        error=payload.error,
        tenant_id=str(appliance.get("tenant_id")) if appliance.get("tenant_id") else None,
    )
    logger.info(
        "hunt result accepted job_id=%s status=%s hits=%s appliance=%s tenant=%s persisted=%s",
        payload.job_id,
        payload.status,
        payload.hit_count,
        appliance.get("id"),
        appliance.get("tenant_id"),
        bool(updated),
    )
    return {
        "accepted": True,
        "job_id": payload.job_id,
        "status": payload.status,
        "persisted": bool(updated),
        "message": "Hunt result accepted",
    }
