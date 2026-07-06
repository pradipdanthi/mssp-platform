#!/usr/bin/env python3
"""
MSSP Platform Toolkit

Commands:
  inventory   Discover the current lab stack and write a manifest
  export      Copy deployable configs into the Git repo
  verify      Check what was exported versus what exists in the live stack

Usage:
  python3 tools/mssp_toolkit.py inventory --stack-dir /home/secadmin/mssp-stack --repo-dir /home/secadmin/mssp-platform
  python3 tools/mssp_toolkit.py export --stack-dir /home/secadmin/mssp-stack --repo-dir /home/secadmin/mssp-platform
  python3 tools/mssp_toolkit.py verify --stack-dir /home/secadmin/mssp-stack --repo-dir /home/secadmin/mssp-platform
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

STACK_DEFAULT = Path("/home/secadmin/mssp-stack")
REPO_DEFAULT = Path("/home/secadmin/mssp-platform")

SAFE_EXTENSIONS = {
    ".yml", ".yaml", ".conf", ".ini", ".xml", ".json", ".toml", ".properties", ".md", ".sh"
}

EXCLUDED_NAMES = {
    ".git", "data", "logs", "log", "backups", "volume", "volumes", "registry", "cache", "tmp"
}

EXCLUDED_FILES = {
    ".env", ".env.local", ".env.prod", ".env.production"
}

SECRET_PATTERNS = re.compile(
    r"(PASS|PASSWORD|SECRET|TOKEN|API_KEY|APIKEY|PRIVATE_KEY|PRIVATE KEY|CERT|COOKIE|AUTH|HASH)",
    re.IGNORECASE,
)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=check)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def is_safe_file(path: Path) -> bool:
    if path.name in EXCLUDED_FILES:
        return True  # export as sanitized template if needed
    if path.suffix.lower() in SAFE_EXTENSIONS:
        return True
    return False


def should_exclude_dir(path: Path) -> bool:
    return path.name in EXCLUDED_NAMES


def walk_files(base: Path) -> Iterable[Path]:
    for root, dirs, files in os.walk(base):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if d not in EXCLUDED_NAMES and d != ".git"]
        for name in files:
            p = root_path / name
            if should_exclude_dir(p.parent):
                continue
            yield p


def sanitize_env(src: Path, dst: Path) -> None:
    ensure_dir(dst.parent)
    out_lines = []
    for raw in src.read_text(errors="ignore").splitlines():
        line = raw.rstrip("\n")
        if not line or line.lstrip().startswith("#"):
            out_lines.append(line)
            continue
        if "=" not in line:
            out_lines.append(line)
            continue
        key, value = line.split("=", 1)
        if SECRET_PATTERNS.search(key) or SECRET_PATTERNS.search(value):
            out_lines.append(f"{key}=__REDACTED__")
        else:
            out_lines.append(line)
    dst.write_text("\n".join(out_lines) + "\n")


def copy_file(src: Path, dst: Path) -> None:
    ensure_dir(dst.parent)
    shutil.copy2(src, dst)


def docker_compose_paths(stack_dir: Path) -> list[Path]:
    candidates = [
        stack_dir / "docker-compose.yml",
        stack_dir / "docker-compose.yaml",
        stack_dir / "compose.yml",
        stack_dir / "compose.yaml",
    ]
    return [p for p in candidates if p.exists()]


def parse_compose_for_services(compose_file: Path) -> dict:
    try:
        import yaml  # type: ignore
    except Exception:
        return {"compose_file": str(compose_file), "note": "PyYAML not installed; basic inventory only."}

    try:
        data = yaml.safe_load(compose_file.read_text())
        services = data.get("services", {}) if isinstance(data, dict) else {}
        return {
            "compose_file": str(compose_file),
            "services": sorted(list(services.keys())),
            "raw_service_count": len(services),
        }
    except Exception as e:
        return {"compose_file": str(compose_file), "error": str(e)}


def inventory(stack_dir: Path, repo_dir: Path) -> Path:
    reports_dir = repo_dir / "reports" / "inventory"
    ensure_dir(reports_dir)

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    manifest_path = reports_dir / f"platform-manifest-{timestamp}.json"

    compose_files = docker_compose_paths(stack_dir)
    if not compose_files:
        raise FileNotFoundError(f"No compose file found in {stack_dir}")

    manifest = {
        "generated_at": dt.datetime.now().isoformat(),
        "stack_dir": str(stack_dir),
        "repo_dir": str(repo_dir),
        "compose_files": [str(p) for p in compose_files],
        "files": [],
        "directories": [],
        "services": [],
    }

    for p in walk_files(stack_dir):
        rel = p.relative_to(stack_dir)
        manifest["files"].append(str(rel))
        if p.is_file() and p.suffix.lower() in SAFE_EXTENSIONS:
            pass

    for p in stack_dir.rglob("*"):
        if p.is_dir() and not should_exclude_dir(p):
            manifest["directories"].append(str(p.relative_to(stack_dir)))

    # service discovery from compose
    compose_inventory = []
    for c in compose_files:
        compose_inventory.append(parse_compose_for_services(c))
    manifest["services"] = compose_inventory

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest_path


def export(stack_dir: Path, repo_dir: Path, manifest_path: Path | None = None) -> None:
    if manifest_path is None:
        inventory_dir = repo_dir / "reports" / "inventory"
        manifests = sorted(inventory_dir.glob("platform-manifest-*.json"))
        if not manifests:
            manifest_path = inventory(stack_dir, repo_dir)
        else:
            manifest_path = manifests[-1]

    manifest = json.loads(manifest_path.read_text())

    # Core paths
    ensure_dir(repo_dir / "docker")
    ensure_dir(repo_dir / "configs")
    ensure_dir(repo_dir / "deployment")
    ensure_dir(repo_dir / "docs" / "runtime-notes")

    # Copy compose file(s)
    for cf in manifest.get("compose_files", []):
        src = Path(cf)
        if src.exists():
            copy_file(src, repo_dir / "docker" / src.name)

    # Copy safe files by extension, preserving relative paths under configs/
    for rel in manifest.get("files", []):
        src = stack_dir / rel
        if not src.exists():
            continue

        # skip compose file because already handled
        if src.name in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
            continue

        # sanitized env
        if src.name == ".env":
            sanitize_env(src, repo_dir / "deployment" / "env" / ".env.example")
            continue

        if not is_safe_file(src):
            continue

        # Preserve top-level component directory under configs/
        dst = repo_dir / "configs" / rel
        copy_file(src, dst)

    # record excluded runtime items
    notes = repo_dir / "docs" / "runtime-notes" / "excluded-runtime-data.txt"
    notes.write_text(
        "\n".join(
            [
                "Excluded from Git on purpose:",
                f"{stack_dir}/wazuh-alerts/alerts.json",
                f"{stack_dir}/wazuh-live-logs/alerts/alerts.json",
                "",
                "Also excluded:",
                "- private keys",
                "- certificates",
                "- databases",
                "- Docker volumes",
                "- logs",
                "- runtime state",
            ]
        )
        + "\n"
    )


def verify(stack_dir: Path, repo_dir: Path) -> None:
    repo_files = set()
    for p in (repo_dir / "docker", repo_dir / "configs", repo_dir / "deployment", repo_dir / "docs", repo_dir / "reports"):
        if p.exists():
            for f in p.rglob("*"):
                if f.is_file():
                    repo_files.add(str(f.relative_to(repo_dir)))

    source_safe = set()
    for p in walk_files(stack_dir):
        if p.name in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
            source_safe.add(str(Path("docker") / p.name))
        elif p.name == ".env":
            source_safe.add("deployment/env/.env.example")
        elif is_safe_file(p):
            source_safe.add(str(Path("configs") / p.relative_to(stack_dir)))

    missing = sorted(source_safe - repo_files)
    extra = sorted(repo_files - source_safe)

    out = repo_dir / "reports" / "validation"
    ensure_dir(out)
    (out / "missing-from-repo.txt").write_text("\n".join(missing) + ("\n" if missing else ""))
    (out / "extra-in-repo.txt").write_text("\n".join(extra) + ("\n" if extra else ""))

    print("Missing from repo:")
    print("\n".join(missing) if missing else "(none)")
    print("\nExtra in repo:")
    print("\n".join(extra) if extra else "(none)")


def main() -> int:
    parser = argparse.ArgumentParser(description="MSSP Platform Toolkit")
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("inventory", "export", "verify"):
        sp = sub.add_parser(name)
        sp.add_argument("--stack-dir", type=Path, default=STACK_DEFAULT)
        sp.add_argument("--repo-dir", type=Path, default=REPO_DEFAULT)

    args = parser.parse_args()
    stack_dir: Path = args.stack_dir
    repo_dir: Path = args.repo_dir

    if args.cmd == "inventory":
        p = inventory(stack_dir, repo_dir)
        print(p)
    elif args.cmd == "export":
        export(stack_dir, repo_dir)
        print("Export complete")
    elif args.cmd == "verify":
        verify(stack_dir, repo_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
