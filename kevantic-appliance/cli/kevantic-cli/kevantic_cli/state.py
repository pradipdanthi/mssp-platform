"""Filesystem paths and JSON state for kevantic-cli."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def state_root() -> Path:
    return Path(
        os.environ.get("KEVANTIC_STATE_DIR")
        or os.environ.get("JUNEXIS_STATE_DIR")
        or "/var/lib/kevantic"
    )


def config_root() -> Path:
    return Path(
        os.environ.get("KEVANTIC_CONFIG_DIR")
        or os.environ.get("JUNEXIS_CONFIG_DIR")
        or "/etc/kevantic"
    )


def nft_profiles_dir() -> Path:
    override = os.environ.get("KEVANTIC_NFT_DIR")
    if override:
        return Path(override)
    # Dev tree: kevantic-appliance/hardening/nftables
    here = Path(__file__).resolve()
    candidate = here.parents[3] / "hardening" / "nftables"
    if candidate.is_dir():
        return candidate
    return config_root() / "nftables"


def ensure_dirs() -> None:
    for p in (
        state_root(),
        state_root() / "secrets",
        state_root() / "ota",
        state_root() / "wpk",
        config_root(),
    ):
        p.mkdir(parents=True, exist_ok=True)
        if p.name == "secrets":
            os.chmod(p, 0o700)


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(path)


def network_mode_path() -> Path:
    return state_root() / "network_mode"


def get_network_mode() -> str:
    p = network_mode_path()
    if not p.is_file():
        return "bootstrap"
    mode = p.read_text(encoding="utf-8").strip()
    return mode if mode in ("bootstrap", "locked") else "bootstrap"


def set_network_mode(mode: str) -> None:
    if mode not in ("bootstrap", "locked"):
        raise ValueError(f"invalid network mode: {mode}")
    ensure_dirs()
    network_mode_path().write_text(mode + "\n", encoding="utf-8")


def default_control_plane() -> str:
    """Lab appliances default to Appliance Management VM 114 (KB-093L).

    Production/public edge: set KEVANTIC_DEFAULT_CONTROL_PLANE=https://soc.kevantic.com
    at image build or in /etc/kevantic/appliance.env before register.
    """
    return (
        os.environ.get("KEVANTIC_DEFAULT_CONTROL_PLANE")
        or os.environ.get("KEVANTIC_CONTROL_PLANE")
        or "http://192.168.0.224:8000"
    ).rstrip("/")


def appliance_state_path() -> Path:
    return state_root() / "appliance.json"


def load_appliance_state() -> dict[str, Any]:
    return _read_json(
        appliance_state_path(),
        {
            "registration": "unregistered",
            "appliance_name": "",
            "site_name": "",
            "control_plane": default_control_plane(),
            "deploy_method": "",
            "appliance_id": None,
        },
    )


def save_appliance_state(data: dict[str, Any]) -> None:
    ensure_dirs()
    _write_json(appliance_state_path(), data)


def bootstrap_state_path() -> Path:
    return state_root() / "bootstrap.json"


def load_bootstrap_state() -> dict[str, Any]:
    return _read_json(
        bootstrap_state_path(),
        {
            "last_result": "never",
            "last_run_at": None,
            "os_updated": False,
            "engines_updated": False,
            "detail": "",
        },
    )


def save_bootstrap_state(data: dict[str, Any]) -> None:
    ensure_dirs()
    _write_json(bootstrap_state_path(), data)


def entitlements_path() -> Path:
    return state_root() / "entitlements.json"


def load_entitlements() -> dict[str, Any]:
    default = {"service_ids": ["svc-01"], "core": True, "raw": None}
    data = _read_json(entitlements_path(), default)
    if not isinstance(data, dict):
        return default
    svc = data.get("service_ids")
    if not isinstance(svc, list):
        data["service_ids"] = list(default["service_ids"])
    return data


def save_entitlements(data: dict[str, Any]) -> None:
    ensure_dirs()
    _write_json(entitlements_path(), data)
