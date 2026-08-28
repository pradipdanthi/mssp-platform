"""Redis-backed login rate limiting (failed attempts per IP and username)."""

from __future__ import annotations

import os
from typing import Optional

from app.db.session import redis_client

LOGIN_RATE_LIMIT_MAX = int(os.getenv("LOGIN_RATE_LIMIT_MAX", "5"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", str(15 * 60)))


class LoginRateLimitExceeded(Exception):
    """Raised when failed login attempts exceed the configured threshold."""


def _ip_key(client_ip: Optional[str]) -> str:
    ip = (client_ip or "unknown").strip()[:64] or "unknown"
    return f"rate_limit:login:{ip}"


def _username_key(email: str) -> str:
    normalized = (email or "").strip().lower()[:320] or "unknown"
    return f"rate_limit:login:{normalized}"


def _attempt_count(key: str) -> int:
    try:
        client = redis_client()
        raw = client.get(key)
        return int(raw) if raw else 0
    except Exception:
        return 0


def check_login_rate_limit(*, client_ip: Optional[str], email: str) -> None:
    """Raise LoginRateLimitExceeded when IP or username is over the threshold."""
    for key in (_ip_key(client_ip), _username_key(email)):
        if _attempt_count(key) >= LOGIN_RATE_LIMIT_MAX:
            raise LoginRateLimitExceeded


def record_failed_login(*, client_ip: Optional[str], email: str) -> None:
    """Increment failed-attempt counters for IP and username."""
    try:
        client = redis_client()
        for key in (_ip_key(client_ip), _username_key(email)):
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
            pipe.execute()
    except Exception:
        return


def reset_login_rate_limit(*, client_ip: Optional[str], email: str) -> None:
    """Clear counters after successful password verification."""
    try:
        client = redis_client()
        client.delete(_ip_key(client_ip), _username_key(email))
    except Exception:
        return
