"""
MISP threat-intel client (VM 108).

Talks to MISP REST API (Authorization header). Compatible with PyMISP restSearch
shapes and the MSSP MISP bridge on :8080.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://192.168.0.218:8080"


class MispClientError(Exception):
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


def base_url() -> str:
    return (os.getenv("MISP_URL") or DEFAULT_URL).strip().rstrip("/")


def api_key() -> str:
    env = (os.getenv("MISP_API_KEY") or "").strip()
    if env:
        return env
    key_file = (os.getenv("MISP_API_KEY_FILE") or "").strip()
    if key_file:
        try:
            return Path(key_file).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return _read_secret_file(
        "/run/secrets/misp_api_key",
        "/opt/mssp-control/.secrets/misp_api_key",
    )


def configured() -> bool:
    return bool(base_url() and api_key())


def health() -> Dict[str, Any]:
    try:
        req = urllib.request.Request(f"{base_url()}/health", method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "unreachable", "error": str(exc)[:200]}


def _post(path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    key = api_key()
    if not key:
        raise MispClientError("MISP API key not configured")
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url()}{path}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        raise MispClientError(f"MISP HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise MispClientError(str(exc)[:300]) from exc


def rest_search_attributes(*, value: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return Attribute dicts from MISP restSearch."""
    body: Dict[str, Any] = {"returnFormat": "json"}
    if value:
        body["value"] = value
    raw = _post("/attributes/restSearch", body)
    # Shapes: {"response":{"Attribute":[...]}} or {"response":[...]}
    resp = raw.get("response") if isinstance(raw, dict) else None
    if isinstance(resp, dict) and "Attribute" in resp:
        attrs = resp["Attribute"]
    elif isinstance(resp, list):
        attrs = []
        for item in resp:
            if isinstance(item, dict) and "Attribute" in item:
                attrs.append(item["Attribute"])
            elif isinstance(item, dict):
                attrs.append(item)
    else:
        attrs = []
    return [a for a in attrs if isinstance(a, dict)]


def list_iocs(limit: int = 500) -> List[Dict[str, Any]]:
    """Normalize MISP attributes into control-plane IOC records."""
    out: List[Dict[str, Any]] = []
    for attr in rest_search_attributes()[:limit]:
        t = (attr.get("type") or "").lower()
        value = str(attr.get("value") or "").strip()
        if not value:
            continue
        if t in ("ip-dst", "ip-src", "ip"):
            ioc_type = "IP"
        elif t in ("domain", "hostname"):
            ioc_type = "DOMAIN"
        elif t in ("md5", "sha1", "sha256", "sha512", "filename|md5", "filename|sha256"):
            ioc_type = "FILE_HASH"
        elif t == "url":
            ioc_type = "URL"
        else:
            ioc_type = "OTHER"
        comment = str(attr.get("comment") or "")
        actor = comment.split(":", 1)[0].strip() if comment else "Unknown"
        out.append(
            {
                "ioc_value": value,
                "ioc_type": ioc_type,
                "threat_actor": actor[:120] or "Unknown",
                "confidence_score": 85,
                "reputation_status": "MALICIOUS",
                "mitre_tactics": [],
                "mitre_techniques": [],
                "summary": comment[:500] or f"Threat indicator from MISP ({t})",
                "recommended_action": "Block or monitor this indicator and hunt for related activity.",
                "source": "misp",
            }
        )
    return out
