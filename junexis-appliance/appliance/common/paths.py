"""Path and environment helpers for the appliance engine."""

from __future__ import annotations

import os
from pathlib import Path


def state_root() -> Path:
    return Path(os.environ.get("JUNEXIS_STATE_DIR", "/var/lib/junexis"))


def log_root() -> Path:
    return Path(os.environ.get("JUNEXIS_LOG_DIR", "/var/log/junexis"))


def datalake_root() -> Path:
    return Path(os.environ.get("JUNEXIS_DATALAKE_DIR", str(log_root() / "datalake")))


def metadata_db_path() -> Path:
    return Path(
        os.environ.get(
            "JUNEXIS_METADATA_DB",
            str(state_root() / "appliance_local.db"),
        )
    )


def telemetry_url() -> str:
    return os.environ.get(
        "JUNEXIS_TELEMETRY_URL",
        "https://api.junexis.com/api/v1/telemetry/ingest",
    )


def hunt_callback_url() -> str:
    return os.environ.get(
        "JUNEXIS_HUNT_CALLBACK_URL",
        "https://api.junexis.com/api/v1/telemetry/hunt-results",
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
