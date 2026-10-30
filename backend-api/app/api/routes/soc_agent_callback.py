"""KB-117: SOC agent → control plane triage callback (service token auth).

Reuses existing security_alerts AI columns. Never auto-contains.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.services import tia_acceptance as acc
from app.services import tia_outbox
from app.services import tia_schema

logger = logging.getLogger(__name__)

router = APIRouter(tags=["soc-agent"])


class TriageResultIn(BaseModel):
    alert_id: str = Field(min_length=1, max_length=64)
    # Binding issued when the control plane opened the attempt (echoed by the agent).
    attempt_id: str = Field(min_length=1, max_length=64)
    job_id: Optional[str] = Field(default=None, max_length=200)
    evidence_version: Optional[str] = Field(default=None, max_length=64)
    tenant_id: Optional[str] = Field(default=None, max_length=64)
    tenant_short_code: Optional[str] = Field(default=None, max_length=64)
    ok: bool = False
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
    # analyst-result-2 fields. Validated server-side in tia_investigation; the
    # agent's own claims are never trusted on their own.
    contract: Optional[str] = Field(default=None, max_length=40)
    execution: Optional[Dict[str, Any]] = None
    disposition: Optional[str] = Field(default=None, max_length=40)
    source_severity: Optional[str] = Field(default=None, max_length=20)
    human_review: Optional[Dict[str, Any]] = None
    limited_evidence: Optional[Dict[str, Any]] = None


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


@router.post("/api/v1/soc-agent/triage-result")
def soc_agent_triage_result(
    payload: TriageResultIn,
    x_soc_agent_token: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Accept an agent callback through the same function the HTTP reply uses.

    Status codes tell the agent what to do:
      200  accepted, or an exact duplicate of an accepted result (stop retrying)
      404  unknown attempt (permanent)
      409  tenant/alert/job/evidence mismatch or a conflicting payload (permanent)
      503  schema not ready or database failure: nothing was recorded, retry later
    """
    _require_agent_token(x_soc_agent_token)
    try:
        result = acc.accept_result(
            source="callback",
            attempt_id=payload.attempt_id,
            claimed_tenant_id=payload.tenant_id,
            claimed_alert_id=payload.alert_id,
            claimed_job_id=payload.job_id,
            claimed_evidence_version=payload.evidence_version,
            raw=payload.model_dump(),
        )
    except tia_schema.SchemaNotReady as exc:
        logger.error("SOC agent callback held: TIA schema not ready alert=%s missing=%s", payload.alert_id, exc.missing)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Result acceptance is not ready; retry later",
        )
    except Exception:  # noqa: BLE001
        logger.exception("SOC agent callback not recorded alert=%s", payload.alert_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Result could not be recorded; retry later",
        )

    if result.status == "rejected":
        code = 404 if result.reason in ("unknown_attempt", "invalid_attempt_id", "alert_missing") else 409
        if result.reason == "attempt_window_expired":
            code = 409
        raise HTTPException(status_code=code, detail=f"Result rejected: {result.reason}")
    if result.status == "conflict":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Conflicting result for the same attempt")

    tia_outbox.kick()
    return {
        "ok": True,
        "status": result.status,
        "reason": result.reason,
        "alert_id": payload.alert_id,
        "attempt_id": result.attempt_id,
        "applied": result.applied,
        "late": result.late,
        "review_item_id": result.review_item_id,
        "review_action": result.review_action,
    }


# ---------------------------------------------------------------------------
# WhatsApp Cloud API delivery receipts (authenticated)
# ---------------------------------------------------------------------------
# Meta signs every POST with HMAC-SHA256 of the raw body using the app secret
# (X-Hub-Signature-256) and verifies the endpoint once with a GET handshake.
# Unsigned or wrongly signed requests change nothing. If the secret is not set
# the endpoint refuses every POST, so delivery stays "unknown" instead of guessed.


def _whatsapp_secret() -> str:
    return (os.getenv("WHATSAPP_APP_SECRET") or "").strip()


def verify_whatsapp_signature(raw_body: bytes, header: Optional[str]) -> bool:
    secret = _whatsapp_secret()
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):].strip())


def extract_whatsapp_statuses(body: Dict[str, Any]) -> list:
    out = []
    for entry in (body.get("entry") or []):
        for change in (entry.get("changes") or []):
            value = change.get("value") or {}
            for st in (value.get("statuses") or []):
                errors = st.get("errors") or []
                detail = ""
                if errors and isinstance(errors[0], dict):
                    detail = f"{errors[0].get('code', '')} {errors[0].get('title', '')}".strip()
                out.append({"id": str(st.get("id") or ""), "status": str(st.get("status") or ""), "error": detail})
    return out


@router.get("/api/v1/notifications/whatsapp/webhook")
def whatsapp_webhook_verify(
    hub_mode: Optional[str] = Query(default=None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(default=None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(default=None, alias="hub.challenge"),
) -> Response:
    expected = (os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN") or "").strip()
    if not expected or hub_mode != "subscribe" or not hub_verify_token or not secrets.compare_digest(hub_verify_token, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="verification failed")
    return Response(content=hub_challenge or "", media_type="text/plain")


@router.post("/api/v1/notifications/whatsapp/webhook")
async def whatsapp_webhook_receive(request: Request, x_hub_signature_256: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    if not _whatsapp_secret():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="delivery receipts are not configured")
    raw = await request.body()
    if not verify_whatsapp_signature(raw, x_hub_signature_256):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")
    try:
        body = json.loads(raw.decode("utf-8"))
        statuses = extract_whatsapp_statuses(body if isinstance(body, dict) else {})
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="malformed receipt payload")
    applied: Dict[str, int] = {}
    try:
        for st in statuses:
            res = tia_outbox.apply_provider_status(st["id"], st["status"], error=st["error"])
            applied[res] = applied.get(res, 0) + 1
    except Exception:  # noqa: BLE001
        logger.exception("delivery receipt not recorded")
        # 5xx makes the provider retry the callback later.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="receipt could not be recorded")
    return {"ok": True, "applied": applied}
