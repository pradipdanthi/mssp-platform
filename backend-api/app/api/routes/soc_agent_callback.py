"""KB-117: SOC agent → control plane triage callback (service token auth).

Reuses existing security_alerts AI columns. Never auto-contains.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.db.session import fetch_one
from app.services.soc_agent_expert import apply_callback_payload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["soc-agent"])


class TriageResultIn(BaseModel):
    alert_id: str = Field(min_length=1, max_length=64)
    tenant_id: Optional[str] = Field(default=None, max_length=64)
    tenant_short_code: Optional[str] = Field(default=None, max_length=64)
    ok: bool = True
    verdict: Optional[str] = None
    confidence: Optional[float] = None
    summary: Optional[str] = None
    root_cause: Optional[str] = None
    containment_suggestion: Optional[str] = None
    enrichment_notes: Optional[str] = None
    recommended_action: Optional[str] = None
    llm: Optional[Dict[str, Any]] = None
    action_package: Optional[Dict[str, Any]] = None
    dossier_id: Optional[str] = None
    llm_meta: Optional[Dict[str, Any]] = None


def _expected_token() -> str:
    # Prefer dedicated callback token; fall back to shared agent token.
    return (
        (os.getenv("SOC_AGENT_CALLBACK_TOKEN") or "").strip()
        or (os.getenv("SOC_AGENT_TOKEN") or "").strip()
    )


def _require_agent_token(x_soc_agent_token: Optional[str]) -> None:
    expected = _expected_token()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SOC agent callback token not configured",
        )
    if not x_soc_agent_token or not secrets.compare_digest(x_soc_agent_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Soc-Agent-Token",
        )


def _resolve_tenant_id(payload: TriageResultIn) -> Optional[str]:
    if payload.tenant_id:
        row = fetch_one(
            "SELECT id::text AS id FROM tenants WHERE id = %s::uuid LIMIT 1;",
            (payload.tenant_id,),
        )
        return (row or {}).get("id")
    if payload.tenant_short_code:
        row = fetch_one(
            "SELECT id::text AS id FROM tenants WHERE upper(short_code) = upper(%s) LIMIT 1;",
            (payload.tenant_short_code,),
        )
        return (row or {}).get("id")
    # Derive from alert
    row = fetch_one(
        "SELECT tenant_id::text AS tenant_id FROM security_alerts WHERE id = %s::uuid LIMIT 1;",
        (payload.alert_id,),
    )
    return (row or {}).get("tenant_id")


@router.post("/api/v1/soc-agent/triage-result")
def soc_agent_triage_result(
    payload: TriageResultIn,
    x_soc_agent_token: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    _require_agent_token(x_soc_agent_token)
    tenant_id = _resolve_tenant_id(payload)
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert or tenant not found")

    alert = fetch_one(
        """
        SELECT id::text AS id, tenant_id::text AS tenant_id, ai_triage_status
        FROM security_alerts
        WHERE id = %s::uuid AND tenant_id = %s::uuid
        LIMIT 1;
        """,
        (payload.alert_id, tenant_id),
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    if (alert.get("ai_triage_status") or "").strip() == "accepted":
        return {
            "ok": True,
            "skipped": "already_accepted",
            "alert_id": payload.alert_id,
        }

    body = payload.model_dump()
    try:
        result = apply_callback_payload(
            alert_id=payload.alert_id,
            tenant_id=tenant_id,
            payload=body,
        )
    except Exception:  # noqa: BLE001
        logger.exception("SOC agent callback persist failed alert=%s", payload.alert_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist triage result",
        )
    return result
