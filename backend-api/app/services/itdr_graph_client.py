"""
Microsoft Graph ITDR client — live Entra ID / M365 identity telemetry.

Requires application credentials (client credentials flow):
  AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
  (or *_FILE secret mounts under /run/secrets / .secrets)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ItdrGraphError(Exception):
    pass


def _read_secret_file(*candidates: str) -> str:
    for candidate in candidates:
        try:
            value = Path(candidate).read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            continue
    return ""


def _env_or_file(env_name: str, *file_candidates: str) -> str:
    direct = (os.getenv(env_name) or "").strip()
    if direct:
        return direct
    file_env = (os.getenv(f"{env_name}_FILE") or "").strip()
    if file_env:
        try:
            return Path(file_env).read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return _read_secret_file(*file_candidates)


def tenant_id() -> str:
    return _env_or_file(
        "AZURE_TENANT_ID",
        "/run/secrets/azure_tenant_id",
        "/opt/mssp-control/.secrets/azure_tenant_id",
    )


def client_id() -> str:
    return _env_or_file(
        "AZURE_CLIENT_ID",
        "/run/secrets/azure_client_id",
        "/opt/mssp-control/.secrets/azure_client_id",
    )


def client_secret() -> str:
    return _env_or_file(
        "AZURE_CLIENT_SECRET",
        "/run/secrets/azure_client_secret",
        "/opt/mssp-control/.secrets/azure_client_secret",
    )


def configured() -> bool:
    return bool(tenant_id() and client_id() and client_secret())


def _token() -> str:
    if not configured():
        raise ItdrGraphError("Microsoft Graph credentials are not configured")
    body = urllib.parse.urlencode(
        {
            "client_id": client_id(),
            "client_secret": client_secret(),
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
    ).encode("utf-8")
    url = f"https://login.microsoftonline.com/{tenant_id()}/oauth2/v2.0/token"
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ItdrGraphError(f"Graph token error: {exc}") from exc
    token = data.get("access_token")
    if not token:
        raise ItdrGraphError("Graph token response missing access_token")
    return str(token)


def _get(path: str, *, top: int = 50) -> Dict[str, Any]:
    token = _token()
    url = f"https://graph.microsoft.com/v1.0{path}"
    if "?" in url:
        url += f"&$top={top}"
    else:
        url += f"?$top={top}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:400]
        raise ItdrGraphError(f"Graph HTTP {exc.code}: {detail}") from exc


def fetch_sign_ins(top: int = 50) -> List[Dict[str, Any]]:
    data = _get("/auditLogs/signIns", top=top)
    return list(data.get("value") or [])


def fetch_directory_audits(top: int = 50) -> List[Dict[str, Any]]:
    data = _get("/auditLogs/directoryAudits", top=top)
    return list(data.get("value") or [])


def normalize_graph_events(
    *,
    domain: str,
    sign_ins: List[Dict[str, Any]],
    audits: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Map Graph payloads to ITDR event samples (customer-safe fields applied later)."""
    events: List[Dict[str, Any]] = []
    for s in sign_ins:
        risk = (s.get("riskLevelAggregated") or s.get("riskLevelDuringSignIn") or "none").lower()
        status = ((s.get("status") or {}).get("errorCode")) or 0
        upn = str(s.get("userPrincipalName") or s.get("userDisplayName") or "unknown@tenant")
        loc = s.get("location") or {}
        country = str(loc.get("countryOrRegion") or "Unknown")
        city = str(loc.get("city") or "Unknown")
        ip = str(s.get("ipAddress") or "0.0.0.0")
        event_type = "SUSPICIOUS_LOGIN"
        if risk in ("high", "medium"):
            event_type = "IMPOSSIBLE_TRAVEL" if risk == "high" else "SUSPICIOUS_LOGIN"
        if int(status or 0) in (500121, 50074, 50076):  # MFA related
            event_type = "MFA_BYPASS_ATTEMPT"
        events.append(
            {
                "upn": upn,
                "event_type": event_type,
                "country": country,
                "city": city,
                "ip": ip,
                "hours_ago": 1,
                "raw": {"source": "microsoft_graph_signIn", "id": s.get("id"), "risk": risk},
            }
        )
    for a in audits:
        activity = str(a.get("activityDisplayName") or "").lower()
        initiated = str(
            ((a.get("initiatedBy") or {}).get("user") or {}).get("userPrincipalName")
            or "unknown@tenant"
        )
        if "add member to role" in activity or "add eligible member" in activity or "role" in activity:
            events.append(
                {
                    "upn": initiated,
                    "event_type": "ROGUE_ADMIN_ASSIGNED",
                    "country": "Cloud",
                    "city": "Directory",
                    "ip": "0.0.0.0",
                    "hours_ago": 2,
                    "raw": {"source": "microsoft_graph_directoryAudit", "id": a.get("id")},
                }
            )
        if "inbox rule" in activity or "forwarding" in activity:
            events.append(
                {
                    "upn": initiated,
                    "event_type": "EXTERNAL_MAIL_FORWARDING",
                    "country": "Cloud",
                    "city": "Exchange",
                    "ip": "0.0.0.0",
                    "hours_ago": 3,
                    "raw": {"source": "microsoft_graph_directoryAudit", "id": a.get("id")},
                }
            )
    # Tag domain for logging only
    for e in events:
        e["tenant_domain"] = domain
    return events
