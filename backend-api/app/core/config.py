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


# ---------------------------------------------------------------------------
# Infrastructure / service endpoints — env-driven with LAN defaults
# ---------------------------------------------------------------------------

class InfraSettings:
    """
    Centralized infrastructure configuration with local LAN defaults.
    These match the existing home-lab demo environment so everything works
    out of the box. Override via environment variables for cloud deployment.
    """

    def __init__(self) -> None:
        self.wazuh_manager_host = _env("WAZUH_MANAGER_HOST", "192.168.0.211")
        self.wazuh_api_url = _env("WAZUH_API_URL", f"https://{self.wazuh_manager_host}:55000")
        self.control_plane_host = _env("CONTROL_PLANE_HOST", "192.168.0.201")
        self.control_plane_url = _env("CONTROL_PLANE_URL", f"http://{self.control_plane_host}:8000")
        self.shuffle_host = _env("SHUFFLE_HOST", "192.168.0.212")
        self.shuffle_webhook_url = _env(
            "SHUFFLE_WEBHOOK_URL",
            f"http://{self.shuffle_host}:3001/api/v1/hooks/webhook",
        )
        self.thehive_host = _env("THEHIVE_HOST", "192.168.0.212")
        self.thehive_url = _env("THEHIVE_URL", f"http://{self.thehive_host}:9000")
        self.greenbone_host = _env("GREENBONE_HOST", "192.168.0.219")
        self.suricata_host = _env("SURICATA_HOST", "192.168.0.216")


@lru_cache
def get_infra_settings() -> InfraSettings:
    return InfraSettings()
