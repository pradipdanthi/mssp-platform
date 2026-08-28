#!/usr/bin/env python3
"""One-time repo rename: Junexis product brand → NikTiar (paths: niktiar, env: NIKTIAR_)."""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

ROOT = Path("/opt/mssp-control")

# Order matters — longer / more specific tokens first.
TEXT_REPLACEMENTS = [
    ("website-junexis", "website-niktiar"),
    ("junexis-website-lab", "niktiar-website-lab"),
    ("junexis-critical-alert-forwarder", "niktiar-critical-alert-forwarder"),
    ("junexis-list-local-agents", "niktiar-list-local-agents"),
    ("junexis-heartbeat", "niktiar-heartbeat"),
    ("junexis_license", "niktiar_license"),
    ("junexis-appliance", "niktiar-appliance"),
    ("junexis_data_lake", "niktiar_data_lake"),
    ("bundle--junexis", "bundle--niktiar"),
    ("/var/log/junexis", "/var/log/niktiar"),
    ("/var/lib/junexis", "/var/lib/niktiar"),
    ("/run/junexis", "/run/niktiar"),
    ("/etc/junexis", "/etc/niktiar"),
    ("/opt/junexis", "/opt/niktiar"),
    ("JUNEXIS_", "NIKTIAR_"),
    ("junexis_cli", "niktiar_cli"),
    ("Junexis", "NikTiar"),
    # OS SSH user on legacy lab VMs — keep lowercase junexis@ for connectivity
]

FILE_RENAMES = [
    ("backend-api/app/services/junexis_license.py", "backend-api/app/services/niktiar_license.py"),
    (
        "kevantic-appliance/configs/systemd/junexis-heartbeat.service",
        "kevantic-appliance/configs/systemd/niktiar-heartbeat.service",
    ),
    (
        "kevantic-appliance/configs/systemd/junexis-heartbeat.timer",
        "kevantic-appliance/configs/systemd/niktiar-heartbeat.timer",
    ),
    (
        "kevantic-appliance/configs/systemd/junexis-critical-alert-forwarder.service",
        "kevantic-appliance/configs/systemd/niktiar-critical-alert-forwarder.service",
    ),
    ("website-junexis/junexis-website-lab.service", "website-niktiar/niktiar-website-lab.service"),
    (".cursor/rules/junexis-appliance.mdc", ".cursor/rules/niktiar-appliance.mdc"),
]

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "postgres_data",
}

SKIP_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".zip", ".deb"}


def should_skip(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return True
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    if path.name == "rename_junexis_to_niktiar.py":
        return True
    return False


def replace_text(content: str) -> str:
    for old, new in TEXT_REPLACEMENTS:
        content = content.replace(old, new)
    return content


def process_files() -> int:
    n = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or should_skip(path):
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "junexis" not in raw.lower() and "JUNEXIS" not in raw:
            continue
        updated = replace_text(raw)
        if updated != raw:
            path.write_text(updated, encoding="utf-8")
            print(f"updated {path.relative_to(ROOT)}")
            n += 1
    return n


def rename_paths() -> None:
    old_web = ROOT / "website-junexis"
    new_web = ROOT / "website-niktiar"
    if old_web.is_dir() and not new_web.exists():
        old_web.rename(new_web)
        print(f"renamed dir {old_web.name} -> {new_web.name}")

    for rel_old, rel_new in FILE_RENAMES:
        src = ROOT / rel_old
        dst = ROOT / rel_new
        if src.is_file() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            print(f"renamed file {rel_old} -> {rel_new}")


def main() -> None:
    rename_paths()
    count = process_files()
    print(f"Done. {count} files updated.")


if __name__ == "__main__":
    main()
