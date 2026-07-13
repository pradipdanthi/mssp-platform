"""
KB-010: Authentication configuration.

Only the settings needed for JWT-based authentication live here. Database
and Redis configuration continue to be read directly in main.py (unchanged)
and in app/db/session.py, so that nothing about the existing, already
validated endpoints depends on this module.
"""

import os
from functools import lru_cache


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class AuthSettings:
    """
    JWT-related settings, read from environment variables only.

    JWT_SECRET must be set in the .env file (and passed through by
    docker-compose.yml) before any /auth/* endpoint can issue or verify a
    token. Nothing in this codebase ever hardcodes a secret value.
    """

    def __init__(self) -> None:
        self.jwt_secret = _env("JWT_SECRET")
        self.jwt_algorithm = _env("JWT_ALGORITHM", "HS256")
        self.jwt_expire_minutes = _env_int("JWT_EXPIRE_MINUTES", 60)

        if not self.jwt_secret:
            raise RuntimeError(
                "JWT_SECRET is not set. Add JWT_SECRET to the .env file and "
                "make sure docker-compose.yml passes it to the backend-api "
                "service, then restart backend-api before using /auth endpoints."
            )


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings()
