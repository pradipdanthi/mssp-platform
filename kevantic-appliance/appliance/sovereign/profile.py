"""NikTiar Sovereign Edge on-appliance profile (air-gap + optional cloud egress)."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROFILE_NAME = "sovereign_edge"
CONFIG_FILENAME = "sovereign-edge.json"
AIRGAP_FILENAME = "sovereign-airgap.json"

# Lab / default control-plane targets blocked when air-gap is enabled.
DEFAULT_BLOCKED_IPV4 = (
    "192.168.0.201",  # mssp-control
    "192.168.0.224",  # appliance-mgmt
)

FORWARDER_UNITS = (
    "kevantic-critical-alert-forwarder.service",
    "niktiar-critical-alert-forwarder.service",
    "junexis-critical-alert-forwarder.service",
)
CHANNELD_UNITS = (
    "kevantic-channeld.service",
    "junexis-channeld.service",
)
HEARTBEAT_TIMERS = (
    "kevantic-heartbeat.timer",
    "niktiar-heartbeat.timer",
    "junexis-heartbeat.timer",
)


def _config_roots() -> List[Path]:
    roots: List[Path] = []
    for env_name in ("KEVANTIC_CONFIG_DIR", "NIKTIAR_CONFIG_DIR", "JUNEXIS_CONFIG_DIR"):
        env = os.environ.get(env_name, "").strip()
        if env:
            roots.append(Path(env))
    for default in (Path("/etc/kevantic"), Path("/etc/niktiar"), Path("/etc/junexis")):
        if default not in roots:
            roots.append(default)
    return roots


def config_paths() -> List[Path]:
    return [root / CONFIG_FILENAME for root in _config_roots()]


def airgap_paths() -> List[Path]:
    return [root / AIRGAP_FILENAME for root in _config_roots()]


def default_profile() -> Dict[str, Any]:
    return {
        "profile": PROFILE_NAME,
        "cloud_egress_enabled": False,
        "offline_license": True,
        "cloud_fleet_visible": False,
        "airgap_enabled": True,
        "blocked_ipv4": list(DEFAULT_BLOCKED_IPV4),
        "applied_at": None,
        "note": "NikTiar Sovereign Edge — air-gapped SOC; cloud egress opt-in only",
    }


def load_profile() -> Dict[str, Any]:
    for path in config_paths():
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
    return default_profile()


def save_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    merged = {**default_profile(), **data, "profile": PROFILE_NAME}
    merged["updated_at"] = int(time.time())
    written: List[str] = []
    for root in _config_roots():
        root.mkdir(parents=True, exist_ok=True)
        path = root / CONFIG_FILENAME
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
        written.append(str(path))
    merged["written_paths"] = written
    return merged


def _run_systemctl(action: str, unit: str, *, dry_run: bool = False) -> Dict[str, Any]:
    cmd = ["systemctl", action, unit]
    if dry_run:
        return {"unit": unit, "action": action, "dry_run": True}
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
    return {
        "unit": unit,
        "action": action,
        "rc": proc.returncode,
        "stderr": (proc.stderr or "")[:200],
    }


def _first_existing_unit(candidates: tuple[str, ...]) -> Optional[str]:
    for unit in candidates:
        proc = subprocess.run(
            ["systemctl", "cat", unit],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if proc.returncode == 0:
            return unit
    return None


def _stop_disable_units(candidates: tuple[str, ...], *, dry_run: bool = False) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    unit = _first_existing_unit(candidates)
    if not unit:
        return out
    out.append(_run_systemctl("stop", unit, dry_run=dry_run))
    out.append(_run_systemctl("disable", unit, dry_run=dry_run))
    return out


def _set_unit_enabled(unit: str, *, enable: bool, dry_run: bool = False) -> List[Dict[str, Any]]:
    actions = ("enable", "start") if enable else ("stop", "disable")
    return [_run_systemctl(action, unit, dry_run=dry_run) for action in actions]


def apply_cloud_egress_posture(
    *,
    enabled: bool,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Enable/disable critical-alert forwarder only; channel stays off in sovereign mode."""
    results: Dict[str, Any] = {"cloud_egress_enabled": enabled, "actions": []}
    forwarder = _first_existing_unit(FORWARDER_UNITS)
    if forwarder:
        results["actions"].extend(_set_unit_enabled(forwarder, enable=enabled, dry_run=dry_run))
    else:
        results["forwarder"] = "not_installed"
    return results


def apply_sovereign_posture(
    profile: Optional[Dict[str, Any]] = None,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Apply sovereign air-gap posture: stop cloud egress, fleet channel, and heartbeat."""
    prof = profile or load_profile()
    actions: List[Dict[str, Any]] = []

    if not prof.get("cloud_egress_enabled", False):
        actions.extend(_stop_disable_units(FORWARDER_UNITS, dry_run=dry_run))
    else:
        actions.extend(
            apply_cloud_egress_posture(enabled=True, dry_run=dry_run).get("actions", [])
        )

    actions.extend(_stop_disable_units(CHANNELD_UNITS, dry_run=dry_run))
    actions.extend(_stop_disable_units(HEARTBEAT_TIMERS, dry_run=dry_run))

    airgap = apply_airgap_firewall(
        blocked_ipv4=prof.get("blocked_ipv4") or list(DEFAULT_BLOCKED_IPV4),
        enabled=bool(prof.get("airgap_enabled", True)),
        dry_run=dry_run,
    )

    prof["applied_at"] = int(time.time())
    if not dry_run:
        save_profile(prof)

    return {
        "ok": True,
        "profile": prof.get("profile"),
        "cloud_egress_enabled": prof.get("cloud_egress_enabled"),
        "airgap_enabled": prof.get("airgap_enabled"),
        "systemd_actions": actions,
        "airgap": airgap,
    }


def apply_airgap_firewall(
    *,
    blocked_ipv4: Optional[List[str]] = None,
    enabled: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Best-effort OUTPUT drops to cloud control-plane IPs (lab + sovereign sites)."""
    targets = [str(ip).strip() for ip in (blocked_ipv4 or DEFAULT_BLOCKED_IPV4) if str(ip).strip()]
    spec = {"enabled": enabled, "blocked_ipv4": targets, "rules": []}
    for root in _config_roots():
        root.mkdir(parents=True, exist_ok=True)
        path = root / AIRGAP_FILENAME
        if not dry_run:
            path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")

    if dry_run:
        spec["dry_run"] = True
        return spec

    for ip in targets:
        # Block NEW outbound sessions to cloud control plane only — keep ESTABLISHED SSH intact.
        cmd = [
            "iptables",
            "-C",
            "OUTPUT",
            "-d",
            ip,
            "-m",
            "conntrack",
            "--ctstate",
            "NEW",
            "-j",
            "REJECT",
        ]
        add_cmd = [
            "iptables",
            "-A",
            "OUTPUT",
            "-d",
            ip,
            "-m",
            "conntrack",
            "--ctstate",
            "NEW",
            "-j",
            "REJECT",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=15)
        if proc.returncode != 0:
            proc = subprocess.run(add_cmd, capture_output=True, text=True, check=False, timeout=15)
        spec["rules"].append(
            {
                "ip": ip,
                "match": "ctstate NEW",
                "rc": proc.returncode,
                "stderr": (proc.stderr or "")[:120],
            }
        )

    return spec


def enable_sovereign_profile(
    *,
    cloud_egress_enabled: bool = False,
    airgap_enabled: bool = True,
    blocked_ipv4: Optional[List[str]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    prof_data = {
        **default_profile(),
        "cloud_egress_enabled": cloud_egress_enabled,
        "airgap_enabled": airgap_enabled,
        "blocked_ipv4": blocked_ipv4 or list(DEFAULT_BLOCKED_IPV4),
    }
    prof = prof_data if dry_run else save_profile(prof_data)
    return apply_sovereign_posture(prof, dry_run=dry_run)


def set_cloud_egress(enabled: bool, *, dry_run: bool = False) -> Dict[str, Any]:
    prof = load_profile()
    prof["cloud_egress_enabled"] = bool(enabled)
    if not dry_run:
        save_profile(prof)
    egress = apply_cloud_egress_posture(enabled=enabled, dry_run=dry_run)
    if enabled:
        # Hybrid bridge: re-allow control-plane egress for forwarder only.
        apply_airgap_firewall(
            blocked_ipv4=prof.get("blocked_ipv4") or list(DEFAULT_BLOCKED_IPV4),
            enabled=False,
            dry_run=dry_run,
        )
    else:
        apply_sovereign_posture(prof, dry_run=dry_run)
    return {"ok": True, "cloud_egress_enabled": enabled, "egress": egress, "profile": prof}


def show_status() -> Dict[str, Any]:
    prof = load_profile()
    forwarder = _first_existing_unit(FORWARDER_UNITS)
    channeld = _first_existing_unit(CHANNELD_UNITS)
    heartbeat = _first_existing_unit(HEARTBEAT_TIMERS)

    def unit_active(unit: Optional[str]) -> Optional[str]:
        if not unit:
            return None
        proc = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return (proc.stdout or "").strip()

    return {
        "profile": prof,
        "units": {
            "forwarder": {"name": forwarder, "active": unit_active(forwarder)},
            "channeld": {"name": channeld, "active": unit_active(channeld)},
            "heartbeat_timer": {"name": heartbeat, "active": unit_active(heartbeat)},
        },
        "config_paths": [str(p) for p in config_paths() if p.is_file()],
    }
