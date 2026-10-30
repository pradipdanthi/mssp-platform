"""HTTP client for the Cursor SOC Analyst Agent (VM 117).

Fail-soft: network/timeouts never raise into ingest paths. Callers treat
None as "agent unavailable — use Ollama deep triage fallback".
"""

from __future__ import annotations

import json
import logging
import os
import socket
import ssl
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


def _truthy(name: str, default: str = "") -> bool:
    return (os.getenv(name) or default).strip().lower() in ("1", "true", "yes", "on")


def agent_transport() -> Dict[str, Any]:
    """Describe the control-plane -> SOC agent transport honestly.

    ``encrypted`` is true only for https with certificate and hostname verification.
    Port 8443 alone says nothing about encryption: the shipped agent unit serves plain
    HTTP there. ``SOC_AGENT_CA_BUNDLE`` pins the internal CA used to verify the agent.
    """
    url = soc_agent_url()
    https = url.lower().startswith("https://")
    bundle = (os.getenv("SOC_AGENT_CA_BUNDLE") or "").strip()
    return {
        "url_scheme": "https" if https else "http",
        "encrypted": https,
        "ca_bundle_configured": bool(bundle),
        "tls_required": _truthy("SOC_AGENT_REQUIRE_TLS"),
        "insecure_allowed": _truthy("SOC_AGENT_ALLOW_INSECURE_HTTP"),
    }


def agent_ssl_context() -> Optional[ssl.SSLContext]:
    """Verifying TLS context for https agent URLs (None for http)."""
    if not soc_agent_url().lower().startswith("https://"):
        return None
    bundle = (os.getenv("SOC_AGENT_CA_BUNDLE") or "").strip()
    ctx = ssl.create_default_context(cafile=bundle or None)
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    cert, key = (os.getenv("SOC_AGENT_CLIENT_CERT") or "").strip(), (os.getenv("SOC_AGENT_CLIENT_KEY") or "").strip()
    if cert and key:  # optional mutual TLS
        ctx.load_cert_chain(cert, key)
    return ctx


def open_agent(req: urllib.request.Request, timeout: float):
    """urlopen for agent calls. Refuses plaintext when SOC_AGENT_REQUIRE_TLS is set."""
    transport = agent_transport()
    if transport["tls_required"] and not transport["encrypted"]:
        raise urllib.error.URLError("agent transport is not encrypted and SOC_AGENT_REQUIRE_TLS is set")
    ctx = agent_ssl_context()
    if ctx is not None:
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)
    return urllib.request.urlopen(req, timeout=timeout)


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


def build_agent_payload(alert: Dict[str, Any], binding: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Normalize a control-plane alert row into the agent ingest contract.

    ``binding`` is the attempt issued by tia_acceptance.open_attempt; the agent echoes
    it on both its HTTP reply and its callback so either can be matched to the
    exact tenant, alert, job and evidence version.
    """
    title = (
        alert.get("alert_title")
        or alert.get("title")
        or "Security alert"
    )
    description = alert.get("alert_description") or alert.get("description") or ""
    payload = {
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
    if binding:
        payload["raw"]["tia"] = {
            key: binding.get(key)
            for key in ("attempt_id", "job_id", "evidence_version", "tenant_id", "alert_id")
        }
    if alert.get("tia_evidence") is not None:
        payload["raw"]["tia_evidence"] = alert["tia_evidence"]
    if alert.get("tia_research_policy") is not None:
        payload["raw"]["research_policy"] = alert["tia_research_policy"]
    return payload


class AgentCallError(Exception):
    """The SOC agent could not produce a usable HTTP answer.

    ``category`` is one of tia_investigation.KNOWN_ERROR_CATEGORIES. Callers turn
    this into a failed Outcome and a durable review item; it is never swallowed
    into "no result".
    """

    def __init__(self, category: str, *, timed_out: bool = False, detail: str = "") -> None:
        super().__init__(category)
        self.category = category
        self.timed_out = timed_out
        self.detail = detail


def call_agent_ingest(
    alert: Dict[str, Any], binding: Optional[Dict[str, Any]] = None, trace: Any = None
) -> Dict[str, Any]:
    """POST one alert to the SOC agent. Returns the parsed JSON object.

    Raises AgentCallError with an explicit category on every failure mode.
    """
    if not soc_agent_enabled():
        raise AgentCallError("agent_disabled")
    token = soc_agent_token()
    if not token:
        logger.warning("SOC_AGENT_ENABLED but SOC_AGENT_TOKEN is empty")
        raise AgentCallError("not_configured", detail="SOC_AGENT_TOKEN empty")

    url = f"{soc_agent_url()}/api/v1/ingest"
    body = json.dumps(build_agent_payload(alert, binding)).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Soc-Agent-Token": token,
            **(trace.headers() if trace is not None else {}),
        },
    )
    alert_ref = alert.get("id") or alert.get("alert_id")
    try:
        with open_agent(req, _timeout_seconds()) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        logger.warning("SOC agent HTTP %s for alert=%s", exc.code, alert_ref)
        if exc.code in (401, 403):
            raise AgentCallError("auth_failure", detail=f"http_{exc.code}") from exc
        if exc.code == 504:
            raise AgentCallError("timeout", timed_out=True, detail="http_504") from exc
        raise AgentCallError("agent_http_error", detail=f"http_{exc.code}") from exc
    except (TimeoutError, socket.timeout) as exc:
        logger.warning("SOC agent timed out for alert=%s", alert_ref)
        raise AgentCallError("timeout", timed_out=True, detail="client_timeout") from exc
    except urllib.error.URLError as exc:
        timed_out = isinstance(exc.reason, (TimeoutError, socket.timeout))
        logger.warning("SOC agent unreachable for alert=%s (%s)", alert_ref, type(exc.reason).__name__)
        if timed_out:
            raise AgentCallError("timeout", timed_out=True, detail="client_timeout") from exc
        raise AgentCallError("agent_unreachable", detail=type(exc.reason).__name__) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("SOC agent call failed for alert=%s (%s)", alert_ref, type(exc).__name__)
        raise AgentCallError("agent_unreachable", detail=type(exc).__name__) from exc

    try:
        data = json.loads(raw) if raw else None
    except ValueError as exc:
        raise AgentCallError("agent_bad_response", detail="not_json") from exc
    if not isinstance(data, dict):
        raise AgentCallError("agent_bad_response", detail="not_object")
    return data


def forward_alert_for_expert_triage(alert: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Legacy soft-fail wrapper: parsed JSON, or None on any failure.

    New code must call call_agent_ingest() so the failure category is preserved.
    """
    if not severity_meets_agent_threshold(alert.get("severity")):
        return None
    try:
        return call_agent_ingest(alert)
    except AgentCallError:
        return None
