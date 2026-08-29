"""Local Sovereign unified portal authentication (air-gapped, stdlib only).

Issues short-lived HMAC-SHA256 JWTs after verifying locally provisioned credentials.
Secrets and password hashes must never be committed to Git.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VALID_ROLES = frozenset(
    {
        "platform_admin",
        "soc_manager",
        "soc_analyst",
        "customer_admin",
        "customer_viewer",
    }
)

DEFAULT_TOKEN_TTL_SECONDS = 3600
PBKDF2_ITERATIONS = 600_000


def _config_roots() -> List[Path]:
    roots: List[Path] = []
    for env_name in ("JUNEXIS_CONFIG_DIR", "KEVANTIC_CONFIG_DIR", "NIKTIAR_CONFIG_DIR"):
        env = os.environ.get(env_name, "").strip()
        if env:
            roots.append(Path(env))
    for default in (Path("/etc/junexis"), Path("/etc/kevantic"), Path("/etc/niktiar")):
        if default not in roots:
            roots.append(default)
    return roots


def users_file_paths() -> List[Path]:
    override = os.environ.get("SOVEREIGN_PORTAL_USERS_FILE", "").strip()
    if override:
        return [Path(override)]
    return [root / "sovereign-portal-users.json" for root in _config_roots()]


def jwt_secret_paths() -> List[Path]:
    override = os.environ.get("SOVEREIGN_PORTAL_JWT_SECRET_FILE", "").strip()
    if override:
        return [Path(override)]
    paths: List[Path] = []
    for root in _config_roots():
        paths.append(root / "secrets" / "sovereign_portal_jwt_secret")
    return paths


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def hash_password(plain_password: str, *, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(plain_password: str, stored: Optional[str]) -> bool:
    if not plain_password or not stored:
        return False
    try:
        scheme, iterations, salt_b64, digest_b64 = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = _b64url_decode(salt_b64)
        expected = _b64url_decode(digest_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def load_users() -> Dict[str, Dict[str, str]]:
    for path in users_file_paths():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        users = data.get("users") if isinstance(data, dict) else None
        if not isinstance(users, list):
            continue
        out: Dict[str, Dict[str, str]] = {}
        for row in users:
            if not isinstance(row, dict):
                continue
            username = str(row.get("username") or "").strip().lower()
            role = str(row.get("role") or "").strip().lower()
            password_hash = str(row.get("password_hash") or "").strip()
            if not username or role not in VALID_ROLES or not password_hash:
                continue
            out[username] = {"role": role, "password_hash": password_hash}
        if out:
            return out
    if os.environ.get("SOVEREIGN_PORTAL_LAB_BOOTSTRAP", "").strip().lower() in ("1", "true", "yes"):
        return _lab_bootstrap_users()
    return {}


def _lab_bootstrap_users() -> Dict[str, Dict[str, str]]:
    """Ephemeral lab users from environment — never persist plaintext to disk."""
    out: Dict[str, Dict[str, str]] = {}
    soc_user = os.environ.get("SOVEREIGN_PORTAL_SOC_USER", "soc_engineer").strip().lower()
    soc_pass = os.environ.get("SOVEREIGN_PORTAL_SOC_PASSWORD", "").strip()
    cust_user = os.environ.get("SOVEREIGN_PORTAL_CUSTOMER_USER", "customer_viewer").strip().lower()
    cust_pass = os.environ.get("SOVEREIGN_PORTAL_CUSTOMER_PASSWORD", "").strip()
    soc_role = os.environ.get("SOVEREIGN_PORTAL_SOC_ROLE", "soc_analyst").strip().lower()
    cust_role = os.environ.get("SOVEREIGN_PORTAL_CUSTOMER_ROLE", "customer_viewer").strip().lower()
    if soc_pass and soc_role in VALID_ROLES:
        out[soc_user] = {"role": soc_role, "password_hash": hash_password(soc_pass)}
    if cust_pass and cust_role in VALID_ROLES:
        out[cust_user] = {"role": cust_role, "password_hash": hash_password(cust_pass)}
    return out


def load_jwt_secret() -> Optional[str]:
    env = os.environ.get("SOVEREIGN_PORTAL_JWT_SECRET", "").strip()
    if env:
        return env
    for path in jwt_secret_paths():
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if text:
                return text
    if os.environ.get("SOVEREIGN_PORTAL_LAB_BOOTSTRAP", "").strip().lower() in ("1", "true", "yes"):
        return os.environ.get("SOVEREIGN_PORTAL_LAB_JWT_SECRET", "sovereign-portal-lab-secret-change-me")
    return None


def authenticate(username: str, password: str) -> Optional[Dict[str, str]]:
    key = (username or "").strip().lower()
    users = load_users()
    row = users.get(key)
    if not row:
        return None
    if not verify_password(password, row.get("password_hash")):
        return None
    return {"username": key, "role": row["role"]}


def issue_access_token(subject: str, role: str, *, ttl_seconds: Optional[int] = None) -> Optional[str]:
    secret = load_jwt_secret()
    if not secret or role not in VALID_ROLES:
        return None
    now = int(time.time())
    ttl = ttl_seconds if ttl_seconds is not None else int(
        os.environ.get("SOVEREIGN_PORTAL_TOKEN_TTL_SECONDS", DEFAULT_TOKEN_TTL_SECONDS)
    )
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + max(60, ttl),
    }
    return _encode_jwt(payload, secret)


def verify_access_token(token: str, *, leeway_seconds: int = 30) -> Optional[Dict[str, Any]]:
    secret = load_jwt_secret()
    if not secret or not token:
        return None
    payload = _decode_jwt(token, secret)
    if not payload:
        return None
    now = int(time.time())
    exp = int(payload.get("exp") or 0)
    if exp and now > exp + leeway_seconds:
        return None
    role = str(payload.get("role") or "").strip().lower()
    if role not in VALID_ROLES:
        return None
    sub = str(payload.get("sub") or "").strip()
    if not sub:
        return None
    return {"sub": sub, "role": role, "exp": exp}


def _encode_jwt(payload: Dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"


def _decode_jwt(token: str, secret: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        header = json.loads(_b64url_decode(header_b64))
        if header.get("alg") != "HS256":
            return None
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_encode(expected), sig_b64):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        return payload if isinstance(payload, dict) else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def parse_bearer_authorization(header_value: Optional[str]) -> Optional[str]:
    text = (header_value or "").strip()
    if not text.lower().startswith("bearer "):
        return None
    token = text[7:].strip()
    return token or None


def login_response(username: str, password: str) -> Tuple[int, Dict[str, Any]]:
    if not load_jwt_secret():
        return 503, {"error": "auth_unconfigured", "detail": "portal JWT secret not provisioned"}
    if not load_users():
        return 503, {"error": "auth_unconfigured", "detail": "portal users not provisioned"}
    identity = authenticate(username, password)
    if not identity:
        return 401, {"error": "invalid_credentials"}
    token = issue_access_token(identity["username"], identity["role"])
    if not token:
        return 503, {"error": "auth_unconfigured"}
    ttl = int(os.environ.get("SOVEREIGN_PORTAL_TOKEN_TTL_SECONDS", DEFAULT_TOKEN_TTL_SECONDS))
    return 200, {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ttl,
        "role": identity["role"],
    }
