"""
KB-brand: CORS allow-list for kevantic.com portal subdomains + lab dev origins.

Browsers only need CORS when the frontend origin differs from the API origin
(e.g. direct :8000 API access or split-host deployments). Production nginx
proxies /api on admin.kevantic.com and portal.kevantic.com same-origin, but
this middleware keeps cross-subdomain and lab/dev flows safe.

Override via CORS_ALLOWED_ORIGINS (comma-separated full origins, no trailing slash).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


# Production + lab defaults — all on root domain kevantic.com (never kevanticcyber.com).
_DEFAULT_ORIGINS: tuple[str, ...] = (
    "https://kevantic.com",
    "https://www.kevantic.com",
    "https://admin.kevantic.com",
    "https://portal.kevantic.com",
    "http://kevantic.com",
    "http://www.kevantic.com",
    "http://admin.kevantic.com",
    "http://portal.kevantic.com",
    # Lab / LAN preview (VM 100)
    "http://192.168.0.201:3000",
    "http://192.168.0.201:3001",
    "http://192.168.0.201:8080",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
)


@lru_cache
def get_cors_allowed_origins() -> List[str]:
    raw = _env("CORS_ALLOWED_ORIGINS", "").strip()
    if raw:
        return [part.strip().rstrip("/") for part in raw.split(",") if part.strip()]
    return list(_DEFAULT_ORIGINS)


@lru_cache
def get_platform_root_domain() -> str:
    """Root domain for portal routing templates (kevantic.com)."""
    return _env("PLATFORM_ROOT_DOMAIN", "kevantic.com").strip().lower() or "kevantic.com"
