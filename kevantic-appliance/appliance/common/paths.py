"""Path and environment helpers for the NikTiar appliance engine."""

from __future__ import annotations

import os
from pathlib import Path


def _env_first(*keys: str, default: str = "") -> str:
    for key in keys:
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return default


def _existing_default(*candidates: str) -> str:
    for c in candidates:
        if Path(c).exists():
            return c
    return candidates[0] if candidates else ""


def state_root() -> Path:
    return Path(
        _env_first(
            "NIKTIAR_STATE_DIR",
            "KEVANTIC_STATE_DIR",
            "JUNEXIS_STATE_DIR",
            default=_existing_default(
                "/var/lib/niktiar",
                "/var/lib/junexis",
                "/var/lib/kevantic",
            ),
        )
    )


def log_root() -> Path:
    return Path(
        _env_first(
            "NIKTIAR_LOG_DIR",
            "KEVANTIC_LOG_DIR",
            "JUNEXIS_LOG_DIR",
            default=_existing_default(
                "/var/log/niktiar",
                "/var/log/junexis",
                "/var/log/kevantic",
            ),
        )
    )


def datalake_root() -> Path:
    explicit = _env_first(
        "NIKTIAR_DATALAKE_DIR",
        "KEVANTIC_DATALAKE_DIR",
        "JUNEXIS_DATALAKE_DIR",
    )
    if explicit:
        return Path(explicit)
    return log_root() / "datalake"


def metadata_db_path() -> Path:
    explicit = _env_first("NIKTIAR_METADATA_DB", "KEVANTIC_METADATA_DB", "JUNEXIS_METADATA_DB")
    if explicit:
        return Path(explicit)
    return state_root() / "appliance_local.db"


def telemetry_url() -> str:
    return _env_first(
        "NIKTIAR_TELEMETRY_URL",
        "KEVANTIC_TELEMETRY_URL",
        "JUNEXIS_TELEMETRY_URL",
        default="https://api.kevantic.com/api/v1/telemetry/ingest",
    )


def hunt_callback_url() -> str:
    return _env_first(
        "NIKTIAR_HUNT_CALLBACK_URL",
        "KEVANTIC_HUNT_CALLBACK_URL",
        "JUNEXIS_HUNT_CALLBACK_URL",
        default="https://api.kevantic.com/api/v1/telemetry/hunt-results",
    )


def ensure_engine_dirs() -> None:
    for p in (
        state_root(),
        state_root() / "secrets",
        state_root() / "telemetry_buffer",
        log_root(),
        datalake_root(),
    ):
        p.mkdir(parents=True, exist_ok=True)
