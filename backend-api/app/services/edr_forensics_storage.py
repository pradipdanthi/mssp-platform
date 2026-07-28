"""KB-084: Local / optional S3 forensic object storage with HMAC-signed URLs."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote, urlencode

from app.core.secrets import read_secret

# Tenant-partitioned keys: {tenant_id}/{endpoint_id}/{timestamp}_{artifact_id}.zip
DEFAULT_STORAGE_ROOT = "/var/lib/mssp/forensics"


def _signing_secret() -> str:
    secret = (
        os.getenv("EDR_FORENSICS_SIGNING_SECRET")
        or read_secret(
            "JWT_SECRET",
            "/run/secrets/jwt_secret",
            "/opt/mssp-control/.secrets/jwt_secret",
        )
        or ""
    ).strip()
    if not secret:
        # Fail closed for URL signing — callers should treat empty as misconfig.
        raise RuntimeError("EDR forensics signing secret is not configured")
    return secret


def storage_root() -> Path:
    root = Path((os.getenv("EDR_FORENSICS_STORAGE_PATH") or DEFAULT_STORAGE_ROOT).strip())
    root.mkdir(parents=True, exist_ok=True)
    return root


def public_api_base() -> str:
    """Base URL agents/Shuffle use for upload/download (include /api if via nginx)."""
    return (
        os.getenv("EDR_PUBLIC_API_BASE")
        or os.getenv("MSSP_PUBLIC_API_BASE")
        or "http://192.168.0.201:8000"
    ).rstrip("/")


def storage_backend() -> str:
    if (os.getenv("EDR_S3_BUCKET") or "").strip():
        return "s3"
    return "local"


def object_key_for(
    *,
    tenant_id: str,
    endpoint_id: str,
    artifact_id: str,
    timestamp_epoch: Optional[int] = None,
) -> str:
    ts = int(timestamp_epoch or time.time())
    ep = (endpoint_id or "unknown").replace("/", "_")[:64]
    return f"{tenant_id}/{ep}/{ts}_{artifact_id}.zip"


def local_path_for_key(object_key: str) -> Path:
    # Prevent path traversal outside storage root.
    root = storage_root().resolve()
    path = (root / object_key).resolve()
    if not str(path).startswith(str(root)):
        raise ValueError("Invalid object key")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _sign(payload: str) -> str:
    return hmac.new(
        _signing_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def make_signed_token(
    *,
    artifact_id: str,
    tenant_id: str,
    purpose: str,
    ttl_seconds: int = 3600,
) -> Tuple[str, int]:
    exp = int(time.time()) + max(60, ttl_seconds)
    payload = f"{purpose}|{artifact_id}|{tenant_id}|{exp}"
    sig = _sign(payload)
    token = f"{exp}.{sig}"
    return token, exp


def verify_signed_token(
    *,
    token: str,
    artifact_id: str,
    tenant_id: str,
    purpose: str,
) -> bool:
    try:
        exp_s, sig = token.split(".", 1)
        exp = int(exp_s)
    except (ValueError, AttributeError):
        return False
    if exp < int(time.time()):
        return False
    payload = f"{purpose}|{artifact_id}|{tenant_id}|{exp}"
    expected = _sign(payload)
    return hmac.compare_digest(expected, sig)


def build_upload_url(*, artifact_id: str, tenant_id: str, ttl_seconds: int = 3600) -> Dict[str, Any]:
    token, exp = make_signed_token(
        artifact_id=artifact_id,
        tenant_id=tenant_id,
        purpose="upload",
        ttl_seconds=ttl_seconds,
    )
    q = urlencode({"token": token})
    # Prefer nginx /api path when PUBLIC base includes host only on :3000/:3001 —
    # default hits FastAPI directly on :8000.
    url = f"{public_api_base()}/v1/edr/forensics/upload/{quote(artifact_id)}?{q}"
    return {
        "upload_url": url,
        "upload_method": "PUT",
        "expires_at_epoch": exp,
        "object_key_hint": None,
        "storage_backend": storage_backend(),
    }


def build_download_url(*, artifact_id: str, tenant_id: str, ttl_seconds: int = 900) -> Dict[str, Any]:
    token, exp = make_signed_token(
        artifact_id=artifact_id,
        tenant_id=tenant_id,
        purpose="download",
        ttl_seconds=ttl_seconds,
    )
    q = urlencode({"token": token})
    url = f"{public_api_base()}/v1/edr/forensics/download/{quote(artifact_id)}?{q}"
    return {
        "download_url": url,
        "expires_at_epoch": exp,
        "ttl_seconds": ttl_seconds,
    }


def write_upload(*, object_key: str, body: bytes) -> Tuple[int, str]:
    path = local_path_for_key(object_key)
    path.write_bytes(body)
    sha = hashlib.sha256(body).hexdigest()
    return len(body), sha


def read_download(*, object_key: str) -> bytes:
    path = local_path_for_key(object_key)
    if not path.is_file():
        raise FileNotFoundError(object_key)
    return path.read_bytes()
