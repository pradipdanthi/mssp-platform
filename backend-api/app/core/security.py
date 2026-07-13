"""
KB-010: Password hashing and JWT helpers.

- Passwords are hashed with bcrypt. Plaintext passwords are never stored,
  logged, or returned by any function here.
- Access tokens are signed JWTs (HS256 by default), verified against the
  JWT_SECRET environment variable. Tokens are short-lived (see
  JWT_EXPIRE_MINUTES in app/core/config.py).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from app.core.config import get_auth_settings


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password for storage. Never store the plaintext itself."""
    password_bytes = plain_password.encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: Optional[str]) -> bool:
    """
    Check a plaintext password against a stored bcrypt hash.

    Returns False (never raises) if there is no hash to compare against, or
    if the stored value is not a valid bcrypt hash - this keeps login safe
    even for accounts that don't have a password set yet.
    """
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, extra_claims: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a signed JWT access token for the given user id (subject).

    extra_claims is merged into the token payload (role, user_type,
    tenant_id) so that dependencies can make fast authorization decisions,
    though app/api/dependencies.py always re-checks the live database too.
    """
    settings = get_auth_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.jwt_expire_minutes)

    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    payload.update(extra_claims)

    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.jwt_expire_minutes * 60,
    }


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode a JWT access token.

    Raises jwt.PyJWTError (or a subclass, e.g. ExpiredSignatureError,
    InvalidSignatureError) if the token is invalid, expired, or was signed
    with a different secret. Callers (see app/api/dependencies.py) turn any
    such failure into a generic 401 response - the specific reason is never
    exposed to the caller, only to server-side logs.
    """
    settings = get_auth_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
