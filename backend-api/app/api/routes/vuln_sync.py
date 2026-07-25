"""KB-069: Greenbone/OpenVAS → control plane vulnerability ingest."""

from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, status

from app.schemas.vulnerabilities import VulnSyncRequest, VulnSyncResponse
from app.services.vuln_sync_service import (
    AssetTenantMismatchError,
    TenantNotFoundError,
    sync_vulnerabilities,
)

router = APIRouter(prefix="/integrations/vuln", tags=["vuln-sync"])


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
    direct = (os.getenv("VULN_SYNC_API_KEY") or "").strip()
    if direct:
        return direct
    key_file = (os.getenv("VULN_SYNC_API_KEY_FILE") or "").strip()
    if key_file:
        try:
            return Path(key_file).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return _read_secret_file(
        "/run/secrets/vuln_sync_api_key",
        "/opt/mssp-control/.secrets/vuln_sync_api_key",
    )


def _require_sync_key(provided: Optional[str]) -> None:
    expected = _configured_sync_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vulnerability sync is not configured",
        )
    if not provided or not hmac.compare_digest(provided.strip(), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid vulnerability sync credentials",
        )


@router.post("/sync", response_model=VulnSyncResponse)
def sync_vuln_findings(
    payload: VulnSyncRequest,
    x_vuln_sync_key: Optional[str] = Header(default=None, alias="X-Vuln-Sync-Key"),
) -> VulnSyncResponse:
    """Ingest normalized Greenbone findings. Never customer-facing raw data."""
    _require_sync_key(x_vuln_sync_key)
    try:
        result = sync_vulnerabilities(payload)
    except TenantNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        ) from None
    except AssetTenantMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None
    return VulnSyncResponse(**result)
