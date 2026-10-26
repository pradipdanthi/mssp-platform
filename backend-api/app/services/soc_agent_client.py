"""HTTP client for the Cursor SOC Analyst Agent (VM 117).

Fail-soft: network/timeouts never raise into ingest paths. Callers treat
None as "agent unavailable — use Ollama deep triage fallback".
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_SEVERITY_RANKS = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def soc_agent_enabled() -> bool:
    return (os.getenv("SOC_AGENT_ENABLED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def soc_agent_url() -> str:
    return (os.getenv("SOC_AGENT_URL") or "http://192.168.0.228:8443").rstrip("/")


def soc_agent_token() -> str:
    return (os.getenv("SOC_AGENT_TOKEN") or "").strip()


def _timeout_seconds() -> float:
    try:
        val = float(os.getenv("SOC_AGENT_TIMEOUT_SECONDS") or "90")
    except ValueError:
        val = 90.0
    return max(5.0, min(val, 300.0))


def _min_severity_rank() -> int:
    raw = (os.getenv("SOC_AGENT_MIN_SEVERITY") or "medium").strip().lower()
    return _SEVERITY_RANKS.get(raw, 2)


def severity_meets_agent_threshold(severity: Optional[str]) -> bool:
    rank = _SEVERITY_RANKS.get((severity or "").strip().lower(), 0)
    return rank >= _min_severity_rank()


def build_agent_payload(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a control-plane alert row into the agent ingest contract."""
    title = (
        alert.get("alert_title")
        or alert.get("title")
        or "Security alert"
    )
    description = alert.get("alert_description") or alert.get("description") or ""
    return {
        "alert_id": str(alert.get("id") or alert.get("alert_id") or ""),
        "title": str(title)[:500],
        "severity": str(alert.get("severity") or "medium").lower(),
        "description": str(description)[:4000] if description else None,
        "source_ip": alert.get("source_ip"),
        "destination_ip": alert.get("destination_ip"),
        "domain": alert.get("destination_host") or alert.get("domain"),
        "hostname": alert.get("asset_hostname")
        or alert.get("destination_host")
        or alert.get("hostname"),
        "tenant": alert.get("short_code") or alert.get("tenant"),
        "source_platform": alert.get("source_tool") or alert.get("source_platform") or "mssp",
        "tags": list(alert.get("tags") or []),
        "raw": {
            "tenant_id": alert.get("tenant_id"),
            "mitre_mapping": alert.get("mitre_mapping"),
            "ai_plain_summary": alert.get("ai_plain_summary"),
            "source_user": alert.get("source_user"),
        },
    }


def forward_alert_for_expert_triage(alert: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """POST one alert to the SOC agent. Returns parsed JSON or None on soft-fail."""
    if not soc_agent_enabled():
        return None
    token = soc_agent_token()
    if not token:
        logger.warning("SOC_AGENT_ENABLED but SOC_AGENT_TOKEN is empty — skip")
        return None
    if not severity_meets_agent_threshold(alert.get("severity")):
        return None

    url = f"{soc_agent_url()}/api/v1/ingest"
    body = json.dumps(build_agent_payload(alert)).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Soc-Agent-Token": token,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_timeout_seconds()) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            if not isinstance(data, dict):
                logger.warning("SOC agent returned non-object JSON")
                return None
            return data
    except urllib.error.HTTPError as exc:
        logger.warning(
            "SOC agent HTTP %s for alert=%s",
            exc.code,
            alert.get("id") or alert.get("alert_id"),
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "SOC agent unreachable for alert=%s: %s",
            alert.get("id") or alert.get("alert_id"),
            exc,
        )
        return None
