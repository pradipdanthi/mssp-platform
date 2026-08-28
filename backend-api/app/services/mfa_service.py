"""TOTP MFA setup, verification, admin controls, and pending-login tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import struct
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from app.core.security import (
    create_mfa_pending_token,
    create_mfa_setup_token,
    decode_mfa_pending_token,
    decode_mfa_setup_token,
)
from app.db.session import execute, fetch_all, fetch_one
from app.services.auth_service import get_user_by_id

MFA_ISSUER = "Kevantic MSSP"
RECOVERY_CODE_COUNT = 8
RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CUSTOMER_ROLES = frozenset({"customer_admin", "customer_viewer"})
logger = logging.getLogger(__name__)


def generate_mfa_secret() -> str:
    """Generate a new base32 TOTP secret."""
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def get_mfa_qr_uri(*, secret: str, email: str) -> str:
    """Build an otpauth:// URI suitable for authenticator apps."""
    label = quote(f"{MFA_ISSUER}:{email}")
    issuer = quote(MFA_ISSUER)
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={issuer}"
        "&algorithm=SHA1&digits=6&period=30"
    )


def _totp_at(secret: str, counter: int, digits: int = 6) -> str:
    key = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10**digits)).zfill(digits)


def verify_mfa_code(secret: Optional[str], code: str, *, window: int = 1) -> bool:
    """Validate a 6-digit TOTP code against a base32 secret."""
    if not secret or code is None:
        return False
    normalized = str(code).strip().replace(" ", "")
    if len(normalized) != 6 or not normalized.isdigit():
        logger.warning(
            "MFA TOTP verification failed: invalid code format server_time=%s received_code=%r",
            int(time.time()),
            normalized,
        )
        return False
    valid_window = window  # ±30 seconds per step (period=30)
    counter = int(time.time()) // 30
    for step in range(-valid_window, valid_window + 1):
        if hmac.compare_digest(_totp_at(secret, counter + step), normalized):
            return True
    logger.warning(
        "MFA TOTP verification failed: code mismatch server_time=%s totp_counter=%s "
        "valid_window=%s received_code=%r expected_current=%r",
        int(time.time()),
        counter,
        valid_window,
        normalized,
        _totp_at(secret, counter),
    )
    return False


# Backward-compatible aliases used by auth routes.
verify_totp_code = verify_mfa_code
build_otpauth_uri = get_mfa_qr_uri


def normalize_recovery_code(code: str) -> str:
    """Normalize XXXX-XXXX recovery codes (dash optional)."""
    cleaned = str(code).strip().upper().replace(" ", "").replace("-", "")
    if len(cleaned) != 8 or not all(ch in RECOVERY_ALPHABET for ch in cleaned):
        raise ValueError("Invalid recovery code format")
    return f"{cleaned[:4]}-{cleaned[4:]}"


def is_recovery_code_format(code: str) -> bool:
    """Heuristic: recovery codes contain letters or a dash; TOTP is 6 digits."""
    normalized = str(code).strip().replace(" ", "")
    if "-" in normalized:
        return True
    if len(normalized) == 8 and not normalized.isdigit():
        return True
    return False


def _hash_recovery_code(code: str) -> str:
    normalized = normalize_recovery_code(code)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> List[str]:
    codes: List[str] = []
    seen: set[str] = set()
    while len(codes) < count:
        part1 = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(4))
        part2 = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(4))
        code = f"{part1}-{part2}"
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def _serialize_recovery_store(codes: List[Dict[str, Any]]) -> str:
    return json.dumps(codes)


def _load_recovery_store(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return json.loads(raw) if raw else []
    if isinstance(raw, list):
        return raw
    return list(raw)


def store_hashed_recovery_codes(user_id: str, plain_codes: List[str]) -> None:
    payload = [{"hash": _hash_recovery_code(code), "used_at": None} for code in plain_codes]
    execute(
        """
        UPDATE platform_users
        SET mfa_recovery_codes = %s::jsonb,
            updated_at = now()
        WHERE id = %s;
        """,
        (_serialize_recovery_store(payload), user_id),
    )


def verify_and_consume_recovery_code(user_id: str, code: str) -> bool:
    row = fetch_one(
        """
        SELECT mfa_recovery_codes
        FROM platform_users
        WHERE id = %s;
        """,
        (user_id,),
    )
    if not row:
        return False
    try:
        target_hash = _hash_recovery_code(code)
    except ValueError:
        return False

    entries = _load_recovery_store(row.get("mfa_recovery_codes"))
    now_iso = datetime.now(timezone.utc).isoformat()
    matched = False
    for entry in entries:
        if entry.get("used_at"):
            continue
        if hmac.compare_digest(str(entry.get("hash", "")), target_hash):
            entry["used_at"] = now_iso
            matched = True
            break
    if not matched:
        return False

    execute(
        """
        UPDATE platform_users
        SET mfa_recovery_codes = %s::jsonb,
            updated_at = now()
        WHERE id = %s;
        """,
        (_serialize_recovery_store(entries), user_id),
    )
    return True


def tenant_enforces_mfa(user: Dict[str, Any]) -> bool:
    """True when the user's tenant (or platform default) requires MFA enrollment."""
    if user.get("role") not in CUSTOMER_ROLES:
        return False
    if user.get("tenant_id") is None:
        return True
    return bool(user.get("tenant_enforce_mfa", True))


def user_requires_mfa_setup(user: Dict[str, Any]) -> bool:
    return tenant_enforces_mfa(user) and not user_requires_mfa(user)


def get_mfa_setup_session(user_id: str) -> Dict[str, str]:
    """Return pending MFA secret + otpauth URI for mandatory setup flow."""
    row = fetch_one(
        """
        SELECT mfa_secret, email
        FROM platform_users
        WHERE id = %s;
        """,
        (user_id,),
    )
    if not row or not row.get("mfa_secret"):
        raise ValueError("MFA setup has not been started")
    return {
        "secret": row["mfa_secret"],
        "otpauth_uri": get_mfa_qr_uri(secret=row["mfa_secret"], email=row["email"]),
    }


def complete_mfa_setup_with_recovery(user_id: str, code: str) -> List[str]:
    """Verify initial TOTP, enable MFA, and issue single-use recovery codes."""
    row = fetch_one(
        """
        SELECT mfa_secret
        FROM platform_users
        WHERE id = %s;
        """,
        (user_id,),
    )
    if not row or not row.get("mfa_secret"):
        raise ValueError("MFA setup has not been started")
    if not verify_mfa_code(row.get("mfa_secret"), code):
        raise ValueError("Invalid MFA code")

    plain_codes = generate_recovery_codes()
    store_hashed_recovery_codes(user_id, plain_codes)
    execute(
        """
        UPDATE platform_users
        SET is_mfa_enabled = TRUE,
            mfa_updated_at = now(),
            updated_at = now()
        WHERE id = %s;
        """,
        (user_id,),
    )
    return plain_codes


def authenticate_mfa_factor(user_id: str, user: Dict[str, Any], code: str) -> Tuple[bool, str]:
    """
    Validate TOTP or a recovery code.
    Returns (ok, factor) where factor is 'totp' or 'recovery'.
    """
    if is_recovery_code_format(code):
        if verify_and_consume_recovery_code(user_id, code):
            return True, "recovery"
        return False, "recovery"
    if verify_mfa_code(user.get("mfa_secret"), code):
        return True, "totp"
    return False, "totp"


def begin_mfa_setup(user_id: str) -> Dict[str, str]:
    """Generate and persist a pending MFA secret (not yet enabled)."""
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("User not found")
    secret = generate_mfa_secret()
    execute(
        """
        UPDATE platform_users
        SET mfa_secret = %s,
            is_mfa_enabled = FALSE,
            mfa_updated_at = now(),
            updated_at = now()
        WHERE id = %s;
        """,
        (secret, user_id),
    )
    return {
        "secret": secret,
        "otpauth_uri": get_mfa_qr_uri(secret=secret, email=user["email"]),
    }


def complete_mfa_setup(user_id: str, code: str) -> None:
    """Verify TOTP and enable MFA for the user."""
    row = fetch_one(
        """
        SELECT mfa_secret, is_mfa_enabled
        FROM platform_users
        WHERE id = %s;
        """,
        (user_id,),
    )
    if not row or not row.get("mfa_secret"):
        raise ValueError("MFA setup has not been started")
    if not verify_mfa_code(row.get("mfa_secret"), code):
        raise ValueError("Invalid MFA code")
    execute(
        """
        UPDATE platform_users
        SET is_mfa_enabled = TRUE,
            mfa_updated_at = now(),
            updated_at = now()
        WHERE id = %s;
        """,
        (user_id,),
    )


def admin_reset_mfa(user_id: str) -> None:
    """Clear MFA for a user who lost their authenticator device."""
    execute(
        """
        UPDATE platform_users
        SET mfa_secret = NULL,
            is_mfa_enabled = FALSE,
            mfa_recovery_codes = NULL,
            mfa_updated_at = now(),
            updated_at = now()
        WHERE id = %s;
        """,
        (user_id,),
    )


def admin_enforce_mfa(user_id: str) -> Dict[str, str]:
    """Provision MFA secret and enable immediately (admin onboarding)."""
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("User not found")
    secret = generate_mfa_secret()
    execute(
        """
        UPDATE platform_users
        SET mfa_secret = %s,
            is_mfa_enabled = TRUE,
            mfa_updated_at = now(),
            updated_at = now()
        WHERE id = %s;
        """,
        (secret, user_id),
    )
    otpauth_url = get_mfa_qr_uri(secret=secret, email=user["email"])
    return {"secret": secret, "otpauth_url": otpauth_url}


def list_mfa_status_rows() -> List[Dict[str, Any]]:
    """Return MFA onboarding status for all platform users."""
    return fetch_all(
        """
        SELECT
            id::text,
            email,
            role,
            tenant_id::text,
            is_mfa_enabled,
            mfa_updated_at::text
        FROM platform_users
        ORDER BY email ASC;
        """
    )


def issue_mfa_pending_token(user_id: str) -> str:
    return create_mfa_pending_token(user_id)


def issue_mfa_setup_token(user_id: str) -> str:
    return create_mfa_setup_token(user_id)


def resolve_mfa_pending_token(mfa_token: str) -> str:
    return decode_mfa_pending_token(mfa_token)


def resolve_mfa_setup_token(setup_token: str) -> str:
    return decode_mfa_setup_token(setup_token)


def user_requires_mfa(user: Dict[str, Any]) -> bool:
    return bool(user.get("is_mfa_enabled")) and bool(user.get("mfa_secret"))
