"""
KB-016: Appliance authentication helpers for the heartbeat receiver
(POST /appliance/heartbeat).

This is a small, appliance-specific counterpart to
app/services/auth_service.py (which handles human JWT/password
authentication) - kept as its own module because the caller here is a
piece of customer-site hardware/software presenting a durable API key via
headers, not a platform_users row presenting a JWT. Nothing here is
imported by, or imports from, auth_service.py, dependencies.py, or
security.py.

Design notes:

- secrets.token_urlsafe(32) yields 256 bits of cryptographically secure
  randomness for the durable appliance API key - the same reasoning
  app/api/routes/appliance_management.py already applies to activation
  tokens: a fast, deterministic hash (SHA-256) is the correct tool for a
  high-entropy, machine-generated secret. bcrypt is deliberately not used
  here - it exists to slow down brute-forcing a low-entropy, human-chosen
  secret such as a password, which does not apply to a 256-bit random
  value.
- The raw appliance API key is never stored - only its SHA-256 hex digest
  (appliance_api_key_hash) and a short, display-only hint (last 6
  characters, appliance_api_key_hint) are persisted.
- Comparison of a presented key's hash against the stored hash uses
  hmac.compare_digest, a constant-time comparison, rather than Python's
  built-in `==`, to reduce the risk of a timing side-channel.
"""

import hashlib
import hmac
import secrets
from typing import Any, Dict, Optional

from app.db.session import fetch_one

RAW_API_KEY_BYTES = 32
API_KEY_HINT_LENGTH = 6


class InvalidApplianceCredentialsError(Exception):
    """
    Raised when the presented X-Appliance-ID/X-Appliance-API-Key pair
    does not identify a real, currently-authenticatable appliance. The
    caller (app/api/routes/appliance_agent.py) turns this into a generic
    401 - deliberately never distinguishing "no such appliance" from
    "wrong key" from "no key has ever been issued to this appliance".
    """


class ApplianceRetiredError(Exception):
    """
    Raised when the presented credentials are valid, but the appliance's
    own status is 'retired'. The caller turns this into a 403 - a known,
    correctly-authenticated identity that is not permitted to send
    heartbeats, distinct from a 401 (no valid identity at all).
    """

    def __init__(self, appliance: Dict[str, Any]):
        self.appliance = appliance
        super().__init__("Appliance is retired")


def hash_secret_sha256(raw_secret: str) -> str:
    """
    SHA-256 hex digest of a raw secret. Used for both activation tokens
    (POST /appliance/register) and durable appliance API keys
    (POST /appliance/heartbeat) - the raw secret is never stored, only
    this digest.
    """
    return hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()


def generate_appliance_api_key() -> "tuple[str, str, str]":
    """
    Generate a new durable appliance API key. Returns
    (raw_key, key_hash, key_hint) - only key_hash and key_hint are ever
    persisted; raw_key is returned to the caller exactly once, in the
    POST /appliance/register response, and is never stored or logged.
    """
    raw_key = secrets.token_urlsafe(RAW_API_KEY_BYTES)
    key_hash = hash_secret_sha256(raw_key)
    key_hint = raw_key[-API_KEY_HINT_LENGTH:]
    return raw_key, key_hash, key_hint


def verify_appliance_credentials(appliance_id: str, raw_api_key: str) -> Dict[str, Any]:
    """
    Look up the appliance by id and verify the presented raw API key
    against its stored hash using a constant-time comparison.

    Raises InvalidApplianceCredentialsError (-> 401) if the appliance does
    not exist, has no credential hash on file, or the presented key does
    not match. Raises ApplianceRetiredError (-> 403) if the credentials
    are valid but the appliance's status is 'retired'. Returns the
    appliance row (dict) on success.
    """
    appliance = fetch_one(
        """
        SELECT id::text, tenant_id::text, appliance_name, site_name, status,
               appliance_uuid, appliance_api_key_hash
        FROM appliances
        WHERE id = %s;
        """,
        (appliance_id,),
    )

    if not appliance:
        raise InvalidApplianceCredentialsError()

    stored_hash: Optional[str] = appliance.get("appliance_api_key_hash")
    if not stored_hash:
        # No credential has ever been issued to this appliance (e.g. a
        # pre-KB-016 row created directly via SQL) - cannot authenticate.
        raise InvalidApplianceCredentialsError()

    presented_hash = hash_secret_sha256(raw_api_key)
    if not hmac.compare_digest(presented_hash, stored_hash):
        raise InvalidApplianceCredentialsError()

    if appliance["status"] == "retired":
        raise ApplianceRetiredError(appliance)

    return appliance
