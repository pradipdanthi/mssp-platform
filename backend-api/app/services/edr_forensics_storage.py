"""KB-084: Local / S3 forensic object storage with HMAC-signed URLs and streaming."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote, urlencode

from app.core.secrets import read_secret

logger = logging.getLogger(__name__)

# Tenant-partitioned keys: {tenant_id}/{endpoint_id}/{timestamp}_{artifact_id}.zip
DEFAULT_STORAGE_ROOT = "/var/lib/mssp/forensics"


def _signing_secret() -> str:
    """Forensic signing key — separate from JWT_SECRET for defense-in-depth."""
    secret = (
        os.getenv("FORENSICS_SIGNING_SECRET")
        or os.getenv("EDR_FORENSICS_SIGNING_SECRET")
        or read_secret(
            "FORENSICS_SIGNING_SECRET",
            "/run/secrets/forensics_signing_secret",
            "/opt/mssp-control/.secrets/forensics_signing_secret",
        )
        or read_secret(
            "JWT_SECRET",
            "/run/secrets/jwt_secret",
            "/opt/mssp-control/.secrets/jwt_secret",
        )
        or ""
    ).strip()
    if not secret:
        raise RuntimeError("EDR forensics signing secret is not configured")
    return secret


def storage_root() -> Path:
    root = Path((os.getenv("EDR_FORENSICS_STORAGE_PATH") or DEFAULT_STORAGE_ROOT).strip())
    root.mkdir(parents=True, exist_ok=True)
    return root


def public_api_base() -> str:
    """Base URL agents/Shuffle use for upload/download (include /api if via nginx)."""
    from app.core.config import get_infra_settings
    return (
        os.getenv("EDR_PUBLIC_API_BASE")
        or os.getenv("MSSP_PUBLIC_API_BASE")
        or get_infra_settings().control_plane_url
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
    """Write upload body (bytes) to local storage."""
    if storage_backend() == "s3":
        return _s3_write(object_key=object_key, body=body)
    path = local_path_for_key(object_key)
    path.write_bytes(body)
    sha = hashlib.sha256(body).hexdigest()
    return len(body), sha


async def write_upload_stream(*, object_key: str, stream, max_bytes: int) -> Tuple[int, str]:
    """
    Stream upload chunks to storage without buffering full body in RAM.
    `stream` is an async iterator yielding bytes chunks (e.g. request.stream()).
    """
    if storage_backend() == "s3":
        return await _s3_write_stream(object_key=object_key, stream=stream, max_bytes=max_bytes)
    path = local_path_for_key(object_key)
    hasher = hashlib.sha256()
    total = 0
    with open(path, "wb") as fh:
        async for chunk in stream:
            total += len(chunk)
            if total > max_bytes:
                # Clean up partial file
                fh.close()
                path.unlink(missing_ok=True)
                raise ValueError(f"Upload exceeds max size ({max_bytes} bytes)")
            hasher.update(chunk)
            fh.write(chunk)
    return total, hasher.hexdigest()


def read_download(*, object_key: str) -> bytes:
    if storage_backend() == "s3":
        return _s3_read(object_key=object_key)
    path = local_path_for_key(object_key)
    if not path.is_file():
        raise FileNotFoundError(object_key)
    return path.read_bytes()


# ---------------------------------------------------------------------------
# S3 backend helpers
# ---------------------------------------------------------------------------

def _s3_bucket() -> str:
    return (os.getenv("EDR_S3_BUCKET") or "mssp-forensics").strip()


def _s3_client():
    """Return a boto3 S3 client (lazy import to avoid hard dep when unused)."""
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("EDR_S3_ENDPOINT") or None,
        region_name=os.getenv("EDR_S3_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("EDR_S3_ACCESS_KEY") or None,
        aws_secret_access_key=os.getenv("EDR_S3_SECRET_KEY") or None,
    )


def _s3_write(*, object_key: str, body: bytes) -> Tuple[int, str]:
    client = _s3_client()
    sha = hashlib.sha256(body).hexdigest()
    client.put_object(Bucket=_s3_bucket(), Key=object_key, Body=body)
    return len(body), sha


async def _s3_write_stream(*, object_key: str, stream, max_bytes: int) -> Tuple[int, str]:
    """Stream upload to S3 via multipart upload."""
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=os.getenv("EDR_S3_ENDPOINT") or None,
        region_name=os.getenv("EDR_S3_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("EDR_S3_ACCESS_KEY") or None,
        aws_secret_access_key=os.getenv("EDR_S3_SECRET_KEY") or None,
        config=Config(signature_version="s3v4"),
    )
    bucket = _s3_bucket()
    mpu = client.create_multipart_upload(Bucket=bucket, Key=object_key)
    upload_id = mpu["UploadId"]
    parts = []
    part_num = 0
    total = 0
    hasher = hashlib.sha256()
    buffer = bytearray()
    PART_SIZE = 8 * 1024 * 1024  # 8MB parts

    try:
        async for chunk in stream:
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"Upload exceeds max size ({max_bytes} bytes)")
            hasher.update(chunk)
            buffer.extend(chunk)
            while len(buffer) >= PART_SIZE:
                part_num += 1
                part_data = bytes(buffer[:PART_SIZE])
                buffer = buffer[PART_SIZE:]
                resp = client.upload_part(
                    Bucket=bucket, Key=object_key, UploadId=upload_id,
                    PartNumber=part_num, Body=part_data,
                )
                parts.append({"PartNumber": part_num, "ETag": resp["ETag"]})
        # Flush remaining buffer
        if buffer:
            part_num += 1
            resp = client.upload_part(
                Bucket=bucket, Key=object_key, UploadId=upload_id,
                PartNumber=part_num, Body=bytes(buffer),
            )
            parts.append({"PartNumber": part_num, "ETag": resp["ETag"]})
        client.complete_multipart_upload(
            Bucket=bucket, Key=object_key, UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
    except Exception:
        client.abort_multipart_upload(Bucket=bucket, Key=object_key, UploadId=upload_id)
        raise

    return total, hasher.hexdigest()


def _s3_read(*, object_key: str) -> bytes:
    client = _s3_client()
    resp = client.get_object(Bucket=_s3_bucket(), Key=object_key)
    return resp["Body"].read()
