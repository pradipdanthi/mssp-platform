"""TheHive API client (org create / verify). Secrets via env/files only."""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from app.core.secrets import read_secret

logger = logging.getLogger(__name__)


class TheHiveClientError(Exception):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def _base_url() -> str:
    return (__import__("os").getenv("THEHIVE_URL", "http://192.168.0.212:9000")).rstrip("/")


def _credentials() -> Tuple[str, str]:
    user = read_secret(
        "THEHIVE_USER",
        "/run/secrets/thehive_user",
        "/opt/mssp-control/.secrets/thehive_user",
    ) or "admin@thehive.local"
    password = read_secret(
        "THEHIVE_PASSWORD",
        "/run/secrets/thehive_password",
        "/opt/mssp-control/.secrets/thehive_password",
    )
    if not password:
        raise TheHiveClientError("TheHive password missing (THEHIVE_PASSWORD file)")
    return user, password


def _default_org() -> str:
    return (__import__("os").getenv("THEHIVE_DEFAULT_ORG", "MSSP")).strip() or "MSSP"


def _request(
    method: str,
    path: str,
    *,
    org: Optional[str] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
) -> Any:
    user, password = _credentials()
    url = _base_url() + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": "Basic "
        + base64.b64encode(f"{user}:{password}".encode()).decode(),
    }
    if org:
        headers["X-Organisation"] = org
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "null"
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise TheHiveClientError(f"TheHive HTTP {exc.code}: {detail}", status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise TheHiveClientError(f"TheHive unreachable: {exc.reason}") from exc


def credentials_configured() -> bool:
    try:
        _credentials()
        return True
    except TheHiveClientError:
        return False


def ensure_organisation(name: str, description: str) -> Dict[str, Any]:
    """
    Ensure a TheHive organisation exists for the tenant.
    Falls back to tag-only mode if org create is not permitted.
    """
    org_name = name.strip()
    if not org_name:
        raise TheHiveClientError("Empty TheHive organisation name")

    # Probe auth against default org first
    _request("GET", "/api/v1/user/current", org=_default_org())

    # Try list orgs (admin)
    try:
        orgs = _request(
            "POST",
            "/api/v1/query",
            org=_default_org(),
            body={"query": [{"_name": "listOrganisation"}]},
        )
        if isinstance(orgs, list):
            for item in orgs:
                if str(item.get("name") or "") == org_name:
                    return {"mode": "provisioned", "org": org_name, "created": False}
    except TheHiveClientError:
        # Non-admin users may not list orgs; continue to create attempt / tag fallback
        pass

    try:
        _request(
            "POST",
            "/api/v1/organisation",
            org=_default_org(),
            body={"name": org_name, "description": description[:500]},
        )
        return {"mode": "provisioned", "org": org_name, "created": True}
    except TheHiveClientError as exc:
        # Permission / license / duplicate → tag-only shared org
        if exc.status in (400, 401, 403, 409):
            return {
                "mode": "tag_only",
                "org": _default_org(),
                "created": False,
                "detail": str(exc)[:200],
            }
        raise
