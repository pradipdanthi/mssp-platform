"""Push expert triage results back to the MSSP control plane (fail-soft)."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def callback_configured() -> bool:
    url = (os.environ.get("MSSP_CALLBACK_URL") or "").strip()
    token = (os.environ.get("MSSP_CALLBACK_TOKEN") or os.environ.get("SOC_AGENT_INGEST_TOKEN") or "").strip()
    return bool(url and token)


def push_triage_result(result: dict[str, Any], alert: dict[str, Any]) -> dict[str, Any] | None:
    """POST /api/v1/soc-agent/triage-result. Never raises into the analyst path."""
    base = (os.environ.get("MSSP_CALLBACK_URL") or "").rstrip("/")
    token = (
        os.environ.get("MSSP_CALLBACK_TOKEN")
        or os.environ.get("SOC_AGENT_INGEST_TOKEN")
        or ""
    ).strip()
    if not base or not token:
        return None

    alert_id = str(result.get("alert_id") or alert.get("alert_id") or "").strip()
    if not alert_id:
        return None

    raw = alert.get("raw") if isinstance(alert.get("raw"), dict) else {}
    tenant_id = raw.get("tenant_id") or alert.get("tenant_id")
    body = {
        "alert_id": alert_id,
        "tenant_id": tenant_id,
        "tenant_short_code": alert.get("tenant"),
        "ok": True,
        "verdict": result.get("verdict"),
        "llm": result.get("llm"),
        "action_package": (result.get("llm") or {}).get("action_package")
        if isinstance(result.get("llm"), dict)
        else result.get("action_package"),
        "dossier_id": result.get("dossier_id"),
        "llm_meta": result.get("llm_meta"),
    }
    url = f"{base}/api/v1/soc-agent/triage-result"
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                url,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Soc-Agent-Token": token,
                },
            )
            if r.status_code >= 400:
                logger.warning("MSSP callback HTTP %s: %s", r.status_code, r.text[:200])
                return None
            return r.json() if r.content else {"ok": True}
    except Exception as exc:  # noqa: BLE001
        logger.warning("MSSP callback failed: %s", exc)
        return None
