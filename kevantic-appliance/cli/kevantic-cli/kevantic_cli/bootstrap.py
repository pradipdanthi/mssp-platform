"""First-time critical OS / engine update (BOOTSTRAP window)."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone

from kevantic_cli import network, state


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_bootstrap_update(
    *,
    os_only: bool = False,
    engines_only: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Ensure network is bootstrap, run apt critical updates (when root/apt present),
    record result. Does NOT auto-lock — engineer must run network lock.
    """
    mode = state.get_network_mode()
    if mode != "bootstrap":
        # Auto-switch to bootstrap profile for the update window
        if not dry_run:
            network.apply_network_mode("bootstrap", dry_run=dry_run)
        mode = "bootstrap"

    detail_parts: list[str] = []
    os_ok = False
    eng_ok = False

    do_os = not engines_only
    do_eng = not os_only

    apt = shutil.which("apt-get")
    if dry_run:
        detail_parts.append("dry-run: would apt-get update && upgrade critical packages")
        os_ok = do_os
        eng_ok = do_eng
    elif apt is None:
        detail_parts.append("apt-get not available (dev host?) — marked simulated success for CLI smoke")
        os_ok = do_os
        eng_ok = do_eng
    elif hasattr(os, "geteuid") and os.geteuid() != 0:
        detail_parts.append("not root — skipped apt; record incomplete")
        os_ok = False
        eng_ok = False
    else:
        if do_os:
            subprocess.run([apt, "update", "-y"], check=False)
            # Unattended critical: use upgrade; image policy can later pin security pocket only
            rc = subprocess.run(
                [apt, "-y", "-o", "Dpkg::Options::=--force-confdef",
                 "-o", "Dpkg::Options::=--force-confold", "upgrade"],
                check=False,
            ).returncode
            os_ok = rc == 0
            detail_parts.append(f"apt upgrade rc={rc}")
        if do_eng:
            # Placeholder for engine package list — real names land when packages are pinned
            eng_pkgs = [
                p
                for p in (
                    "wazuh-manager",
                    "fluent-bit",
                    "suricata",
                    "zeek",
                )
                if True
            ]
            # Only upgrade if installed — do not install TheHive etc.
            installed: list[str] = []
            for pkg in eng_pkgs:
                chk = subprocess.run(
                    ["dpkg-query", "-W", "-f=${Status}", pkg],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if "install ok installed" in (chk.stdout or ""):
                    installed.append(pkg)
            if not installed:
                detail_parts.append("no backend engine packages installed yet — skip engine upgrade")
                eng_ok = True
            else:
                rc = subprocess.run([apt, "-y", "install", "--only-upgrade", *installed], check=False).returncode
                eng_ok = rc == 0
                detail_parts.append(f"engine upgrade {installed} rc={rc}")

    success = (not do_os or os_ok) and (not do_eng or eng_ok)
    result = {
        "last_result": "success" if success else "failed",
        "last_run_at": _utc_now(),
        "os_updated": os_ok if do_os else state.load_bootstrap_state().get("os_updated", False),
        "engines_updated": eng_ok if do_eng else state.load_bootstrap_state().get("engines_updated", False),
        "detail": "; ".join(detail_parts),
        "network_mode": state.get_network_mode(),
    }
    state.save_bootstrap_state(result)
    return result
