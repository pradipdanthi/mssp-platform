"""
Velociraptor DFIR client — control plane → VM 110 bridge (HTTP :8001).

Triggers collect_artifacts / dump_RAM / fetch_MFT / get_process_memory style jobs.
Never returns raw evidence bytes to customer APIs.
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

DEFAULT_BRIDGE_URL = "http://192.168.0.220:8001"


class VelociraptorClientError(Exception):
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


def bridge_base_url() -> str:
    return (
        os.getenv("VELOCIRAPTOR_SERVER_URL")
        or os.getenv("VELOCIRAPTOR_BRIDGE_URL")
        or DEFAULT_BRIDGE_URL
    ).strip().rstrip("/")


def bridge_api_key() -> str:
    env = (os.getenv("VELOCIRAPTOR_BRIDGE_API_KEY") or "").strip()
    if env:
        return env
    key_file = (os.getenv("VELOCIRAPTOR_BRIDGE_API_KEY_FILE") or "").strip()
    if key_file:
        try:
            return Path(key_file).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return _read_secret_file(
        "/run/secrets/velociraptor_bridge_api_key",
        "/opt/mssp-control/.secrets/velociraptor_bridge_api_key",
    )


def configured() -> bool:
    return bool(bridge_base_url() and bridge_api_key())


def health() -> Dict[str, Any]:
    url = f"{bridge_base_url()}/health"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "unreachable", "error": str(exc)[:200], "url": url}


def _post(path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    key = bridge_api_key()
    if not key:
        raise VelociraptorClientError("Velociraptor bridge API key not configured")
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{bridge_base_url()}{path}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Velociraptor-Bridge-Key": key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        raise VelociraptorClientError(f"bridge HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise VelociraptorClientError(str(exc)[:300]) from exc


def collect(
    *,
    action: str,
    hostname: str,
    tenant_id: str,
    execution_id: Optional[str] = None,
    artifacts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Start a DFIR collection on VM 110.
    action: collect_artifacts | dump_RAM | fetch_MFT | get_process_memory
    """
    payload: Dict[str, Any] = {
        "action": action,
        "hostname": hostname,
        "tenant_id": tenant_id,
        "execution_id": execution_id or "",
    }
    if artifacts:
        payload["artifacts"] = artifacts
    return _post("/v1/collect", payload)


def collect_artifacts(**kwargs: Any) -> Dict[str, Any]:
    return collect(action="collect_artifacts", **kwargs)


def dump_ram(**kwargs: Any) -> Dict[str, Any]:
    return collect(action="dump_RAM", **kwargs)


def fetch_mft(**kwargs: Any) -> Dict[str, Any]:
    return collect(action="fetch_MFT", **kwargs)


def get_process_memory(**kwargs: Any) -> Dict[str, Any]:
    return collect(action="get_process_memory", **kwargs)
