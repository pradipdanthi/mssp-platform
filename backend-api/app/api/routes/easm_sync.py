"""Integrations: EASM scan-plan + sync for VM 109 agent."""

from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.services.easm_scan_plan_service import build_easm_scan_plan, ingest_easm_sync

router = APIRouter(prefix="/integrations/easm", tags=["easm-sync"])


def _read_secret_file(*candidates: str) -> str:
    for candidate in candidates:
        try:
            value = Path(candidate).read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            continue
    return ""


def _configured_sync_key() -> str:
    direct = (os.getenv("EASM_SYNC_API_KEY") or "").strip()
    if direct:
        return direct
    key_file = (os.getenv("EASM_SYNC_API_KEY_FILE") or "").strip()
    if key_file:
        try:
            return Path(key_file).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    # Prefer dedicated secret; fall back to vuln sync key for co-located VM 109 ops.
    return _read_secret_file(
        "/run/secrets/easm_sync_api_key",
        "/opt/mssp-control/.secrets/easm_sync_api_key",
        "/run/secrets/vuln_sync_api_key",
        "/opt/mssp-control/.secrets/vuln_sync_api_key",
    )


def _require_sync_key(provided: Optional[str]) -> None:
    expected = _configured_sync_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EASM sync is not configured",
        )
    if not provided or not hmac.compare_digest(provided.strip(), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid EASM sync credentials",
        )


class EasmAssetIn(BaseModel):
    domain_or_ip: str = Field(min_length=1, max_length=255)
    asset_type: str = "SUBDOMAIN"
    discovery_source: str = "amass_passive"


class EasmFindingIn(BaseModel):
    asset_name: str = Field(default="", max_length=255)
    finding_type: str = "EXPOSURE"
    severity: str = "MEDIUM"
    title: str = "External finding"
    description: str = ""
    remediation: str = ""


class EasmSyncRequest(BaseModel):
    tenant_short_code: Optional[str] = None
    tenant_id: Optional[str] = None
    target_domain: str = Field(min_length=1, max_length=255)
    engine: str = "AMASS_NUCLEI"
    assets: list[EasmAssetIn] = Field(default_factory=list)
    findings: list[EasmFindingIn] = Field(default_factory=list)


@router.get("/scan-plan")
def get_easm_scan_plan(
    x_easm_sync_key: Optional[str] = Header(default=None, alias="X-Easm-Sync-Key"),
    force: bool = False,
) -> Dict[str, Any]:
    _require_sync_key(x_easm_sync_key)
    return build_easm_scan_plan(force_all=force)


@router.post("/sync")
def sync_easm_findings(
    payload: EasmSyncRequest,
    x_easm_sync_key: Optional[str] = Header(default=None, alias="X-Easm-Sync-Key"),
) -> Dict[str, Any]:
    _require_sync_key(x_easm_sync_key)
    try:
        return ingest_easm_sync(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
