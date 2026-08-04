"""Apply bootstrap vs locked nftables profiles."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from junexis_cli import state


def profile_path(mode: str) -> Path:
    name = "locked.nft" if mode == "locked" else "bootstrap.nft"
    return state.nft_profiles_dir() / name


def apply_network_mode(mode: str, *, dry_run: bool = False) -> str:
    """Set mode file and optionally load nftables. Returns human message."""
    path = profile_path(mode)
    if not path.is_file():
        raise FileNotFoundError(f"nftables profile missing: {path}")

    state.set_network_mode(mode)

    if dry_run:
        return f"network_mode={mode} (dry-run; would apply {path})"

    nft = shutil.which("nft")
    if nft is None:
        # Image may not have nft yet — still persist mode for status/handoff checks
        return (
            f"network_mode={mode} recorded; nft not installed — "
            f"profile ready at {path} (install nftables on appliance image)"
        )

    # Copy into /etc/junexis/nftables when writable
    dest_dir = state.config_root() / "nftables"
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / path.name
        dest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        apply_target = dest
    except OSError:
        apply_target = path

    try:
        subprocess.run([nft, "-f", str(apply_target)], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        # Do not leave operator without mode file — but surface failure
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"nft apply failed: {err}") from exc
    except PermissionError:
        return (
            f"network_mode={mode} recorded; need root to apply nftables "
            f"({apply_target})"
        )

    return f"network_mode={mode}; applied {apply_target}"


def require_root_hint() -> None:
    if hasattr(os := __import__("os"), "geteuid") and os.geteuid() != 0:
        print("note: nftables apply may require root", file=sys.stderr)
