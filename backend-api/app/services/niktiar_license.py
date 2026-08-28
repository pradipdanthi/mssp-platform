"""Kevantic appliance license JWS (EdDSA / Ed25519) — mint only on control plane."""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)

# Canonical issuer — must match appliance license_ops.py / license_verify.py.
ISSUER = "kevantic-license"
ALLOWED_SERVICES = {
    "svc-01",
    "svc-02",
    "svc-03",
    "svc-04",
    "svc-05",
    "svc-06",
    "svc-07",
    "svc-08",
    "svc-09",
    "svc-10",
}


class LicenseSigningError(RuntimeError):
    pass


class LicenseVerifyError(ValueError):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


_PRIVATE_KEY_ENV_PAIRS = (
    ("KEVANTIC_LICENSE_PRIVATE_KEY_PEM", "KEVANTIC_LICENSE_PRIVATE_KEY_FILE"),
    ("NIKTIAR_LICENSE_PRIVATE_KEY_PEM", "NIKTIAR_LICENSE_PRIVATE_KEY_FILE"),
)


def load_private_key_from_env() -> Ed25519PrivateKey:
    """
    Load Ed25519 private key from (first match wins):
      KEVANTIC_LICENSE_PRIVATE_KEY_PEM / KEVANTIC_LICENSE_PRIVATE_KEY_FILE
      NIKTIAR_LICENSE_PRIVATE_KEY_PEM / NIKTIAR_LICENSE_PRIVATE_KEY_FILE
    PEM text may use literal \\n. Never log key material.
    """
    for pem_var, file_var in _PRIVATE_KEY_ENV_PAIRS:
        pem = os.environ.get(pem_var, "").strip()
        if pem:
            pem_bytes = pem.replace("\\n", "\n").encode("utf-8")
            key = load_pem_private_key(pem_bytes, password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise LicenseSigningError(f"{pem_var} is not Ed25519")
            return key
        path = os.environ.get(file_var, "").strip()
        if path:
            key = load_pem_private_key(Path(path).read_bytes(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise LicenseSigningError(f"{file_var} is not Ed25519")
            return key
    raise LicenseSigningError(
        "License signing key not configured "
        "(set KEVANTIC_LICENSE_PRIVATE_KEY_PEM or KEVANTIC_LICENSE_PRIVATE_KEY_FILE; "
        "NIKTIAR_LICENSE_PRIVATE_KEY_* aliases are also accepted)"
    )


def generate_keypair() -> tuple[bytes, bytes]:
    """Return (private_pem, public_pem)."""
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    pub_pem = priv.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    return priv_pem, pub_pem


def mint_license(
    *,
    tenant_id: str,
    service_ids: Sequence[str],
    appliance_id: Optional[str] = None,
    fingerprint: Optional[str] = None,
    contract_id: Optional[str] = None,
    core: bool = False,
    min_term_years: int = 1,
    ttl_seconds: int = 365 * 24 * 3600,
    private_key: Optional[Ed25519PrivateKey] = None,
) -> Dict[str, Any]:
    """Create compact JWS license. Only call from Admin/control-plane paths."""
    if min_term_years < 1:
        raise LicenseSigningError("min_term_years must be >= 1")
    svc = []
    for s in service_ids:
        sid = str(s).strip().lower()
        if sid not in ALLOWED_SERVICES:
            raise LicenseSigningError(f"Unknown service id: {s}")
        if sid not in svc:
            svc.append(sid)
    if core and "svc-01" not in svc:
        svc.insert(0, "svc-01")
    if not svc:
        raise LicenseSigningError("service_ids must not be empty")

    key = private_key or load_private_key_from_env()
    now = int(time.time())
    claims: Dict[str, Any] = {
        "iss": ISSUER,
        "sub": str(tenant_id),
        "svc": svc,
        "core": bool(core),
        "nbf": now,
        "iat": now,
        "exp": now + int(ttl_seconds),
        "jti": str(uuid.uuid4()),
        "min_term_years": int(min_term_years),
    }
    if appliance_id:
        claims["aid"] = str(appliance_id)
    if fingerprint:
        claims["fp"] = str(fingerprint)
    if contract_id:
        claims["contract"] = str(contract_id)

    header = {"alg": "EdDSA", "typ": "JWT"}
    h_b64 = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    p_b64 = _b64url(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    sig = key.sign(signing_input)
    token = f"{h_b64}.{p_b64}.{_b64url(sig)}"
    return {"license_jws": token, "claims": claims}


def verify_license(
    token: str,
    *,
    public_key_pem: bytes,
    fingerprint: Optional[str] = None,
    skew_seconds: int = 300,
) -> Dict[str, Any]:
    pub = load_pem_public_key(public_key_pem)
    if not isinstance(pub, Ed25519PublicKey):
        raise LicenseVerifyError("public key is not Ed25519")
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise LicenseVerifyError("not a compact JWS")
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    try:
        pub.verify(_b64url_decode(parts[2]), signing_input)
    except Exception as exc:  # noqa: BLE001
        raise LicenseVerifyError("invalid signature") from exc
    header = json.loads(_b64url_decode(parts[0]))
    if header.get("alg") != "EdDSA":
        raise LicenseVerifyError("unsupported alg")
    claims = json.loads(_b64url_decode(parts[1]))
    now = int(time.time())
    if int(claims.get("nbf", 0)) > now + skew_seconds:
        raise LicenseVerifyError("not yet valid")
    if int(claims.get("exp", 0)) < now - skew_seconds:
        raise LicenseVerifyError("expired")
    if claims.get("iss") != ISSUER:
        raise LicenseVerifyError("bad issuer")
    if fingerprint and claims.get("fp") and claims["fp"] != fingerprint:
        raise LicenseVerifyError("fingerprint mismatch")
    return claims
