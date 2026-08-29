"""Sovereign Edge full local stack (TheHive, Shuffle, unified portal).

Modes:
- preflight: compose + manifest only (golden bake / air-gap staging)
- stub: lightweight loopback stubs for lab validation on small appliances
- docker: real TheHive + Shuffle compose stacks (VM199+ with Docker + RAM)
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROFILE_NAME = "sovereign_full_stack"
CONFIG_FILENAME = "sovereign-full-stack.json"
MARKER_FILENAME = "installed"
MODES = ("preflight", "stub", "docker")

DEFAULT_THEHIVE_PORT = 9000
DEFAULT_SHUFFLE_PORT = 3001
DEFAULT_PORTAL_PORT = 9443
MIN_DOCKER_RAM_MB = 12288


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


def install_roots() -> List[Path]:
    roots: List[Path] = []
    for env_name in ("KEVANTIC_INSTALL_ROOT", "NIKTIAR_INSTALL_ROOT", "JUNEXIS_INSTALL_ROOT"):
        env = os.environ.get(env_name, "").strip()
        if env:
            roots.append(Path(env))
    for default in (
        Path("/opt/kevantic/sovereign-full-stack"),
        Path("/opt/niktiar/sovereign-full-stack"),
        Path("/opt/junexis/sovereign-full-stack"),
    ):
        if default not in roots:
            roots.append(default)
    return roots


def state_dir() -> Path:
    env = os.environ.get("SOVEREIGN_FULL_STACK_STATE_DIR", "").strip()
    if env:
        return Path(env)
    for candidate in (Path("/var/lib/junexis/sovereign-full-stack"), Path("/var/lib/kevantic/sovereign-full-stack")):
        if candidate.parent.is_dir():
            return candidate
    return Path("/var/lib/junexis/sovereign-full-stack")


def compose_source_dir() -> Path:
    for base in (
        Path("/opt/junexis/appliance-src/appliance/sovereign/compose"),
        Path("/opt/kevantic/appliance-src/appliance/sovereign/compose"),
    ):
        if base.is_dir():
            return base
    here = Path(__file__).resolve().parent / "compose"
    return here


def default_manifest(*, mode: str = "preflight") -> Dict[str, Any]:
    return {
        "profile": PROFILE_NAME,
        "mode": mode if mode in MODES else "preflight",
        "thehive_port": DEFAULT_THEHIVE_PORT,
        "shuffle_port": DEFAULT_SHUFFLE_PORT,
        "unified_portal_port": DEFAULT_PORTAL_PORT,
        "thehive_url": f"http://127.0.0.1:{DEFAULT_THEHIVE_PORT}",
        "shuffle_url": f"http://127.0.0.1:{DEFAULT_SHUFFLE_PORT}",
        "unified_portal_url": f"http://127.0.0.1:{DEFAULT_PORTAL_PORT}",
        "note": "NikTiar Sovereign Edge — local TheHive, Shuffle, unified portal",
        "applied_at": None,
    }


def load_manifest() -> Dict[str, Any]:
    for root in _config_roots():
        path = root / CONFIG_FILENAME
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
    return default_manifest()


def save_manifest(data: Dict[str, Any]) -> Dict[str, Any]:
    merged = {**default_manifest(mode=str(data.get("mode") or "preflight")), **data, "profile": PROFILE_NAME}
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


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    proc = subprocess.run(["docker", "info"], capture_output=True, text=True, check=False, timeout=20)
    return proc.returncode == 0


def _mem_total_mb() -> int:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 0


def recommend_mode() -> str:
    if _docker_available() and _mem_total_mb() >= MIN_DOCKER_RAM_MB:
        return "docker"
    return "stub"


def install_compose_files() -> Dict[str, Any]:
    src = compose_source_dir()
    installed: List[str] = []
    for root in install_roots():
        root.mkdir(parents=True, exist_ok=True)
        for name in ("thehive-docker-compose.yml", "shuffle-docker-compose.yml"):
            src_file = src / name
            if not src_file.is_file():
                continue
            dest = root / name
            shutil.copy2(src_file, dest)
            installed.append(str(dest))
    marker = state_dir() / MARKER_FILENAME
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"installed_at={int(time.time())}\n", encoding="utf-8")
    return {"ok": True, "installed": installed, "marker": str(marker)}


def _run(cmd: List[str], *, cwd: Optional[Path] = None, timeout: int = 600) -> Dict[str, Any]:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=False, timeout=timeout)
    return {
        "cmd": cmd,
        "rc": proc.returncode,
        "stdout": (proc.stdout or "")[:500],
        "stderr": (proc.stderr or "")[:500],
    }


def start_docker_stacks(manifest: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = manifest or load_manifest()
    if not _docker_available():
        return {"ok": False, "error": "docker_unavailable"}
    root = install_roots()[0]
    thehive = root / "thehive-docker-compose.yml"
    shuffle = root / "shuffle-docker-compose.yml"
    actions: List[Dict[str, Any]] = []
    if thehive.is_file():
        actions.append(_run(["docker", "compose", "-f", str(thehive), "up", "-d"], timeout=900))
    if shuffle.is_file():
        actions.append(_run(["docker", "compose", "-f", str(shuffle), "up", "-d"], timeout=900))
    ok = all(a.get("rc") == 0 for a in actions) if actions else False
    if ok:
        data["mode"] = "docker"
        save_manifest(data)
    return {"ok": ok, "actions": actions}


def stop_docker_stacks() -> Dict[str, Any]:
    root = install_roots()[0]
    actions: List[Dict[str, Any]] = []
    for name in ("thehive-docker-compose.yml", "shuffle-docker-compose.yml"):
        compose = root / name
        if compose.is_file():
            actions.append(_run(["docker", "compose", "-f", str(compose), "down"], timeout=300))
    return {"ok": True, "actions": actions}


def enable_profile(*, mode: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    chosen = mode or os.environ.get("SOVEREIGN_FULL_STACK_MODE", "").strip() or recommend_mode()
    if chosen not in MODES:
        chosen = "preflight"
    manifest = default_manifest(mode=chosen)
    manifest["applied_at"] = int(time.time())
    if dry_run:
        return {"ok": True, "dry_run": True, "manifest": manifest}
    install_compose_files()
    save_manifest(manifest)
    result: Dict[str, Any] = {"ok": True, "manifest": manifest}
    if chosen == "stub":
        result["stub"] = start_stub_services(manifest)
    elif chosen == "docker":
        result["docker"] = start_docker_stacks(manifest)
    return result


def start_stub_services(manifest: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = manifest or load_manifest()
    script = Path("/usr/local/sbin/sovereign-full-stack-stub")
    if not script.is_file():
        return {"ok": False, "error": "stub_script_missing"}
    proc = subprocess.Popen(
        [str(script), "start"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    proc.wait(timeout=10)
    data["mode"] = "stub"
    save_manifest(data)
    return {"ok": proc.returncode == 0, "rc": proc.returncode}


def stop_stub_services() -> Dict[str, Any]:
    script = Path("/usr/local/sbin/sovereign-full-stack-stub")
    if not script.is_file():
        return {"ok": True, "skipped": True}
    proc = subprocess.run([str(script), "stop"], capture_output=True, text=True, check=False, timeout=30)
    return {"ok": proc.returncode == 0, "rc": proc.returncode}


def show_status() -> Dict[str, Any]:
    manifest = load_manifest()
    th_port = int(manifest.get("thehive_port") or DEFAULT_THEHIVE_PORT)
    sh_port = int(manifest.get("shuffle_port") or DEFAULT_SHUFFLE_PORT)
    portal_port = int(manifest.get("unified_portal_port") or DEFAULT_PORTAL_PORT)
    return {
        "ok": True,
        "manifest": manifest,
        "docker_available": _docker_available(),
        "mem_total_mb": _mem_total_mb(),
        "recommended_mode": recommend_mode(),
        "ports": {
            "thehive": {"port": th_port, "open": _port_open("127.0.0.1", th_port)},
            "shuffle": {"port": sh_port, "open": _port_open("127.0.0.1", sh_port)},
            "unified_portal": {"port": portal_port, "open": _port_open("127.0.0.1", portal_port)},
        },
        "compose_installed": any((r / "thehive-docker-compose.yml").is_file() for r in install_roots()),
        "install_marker": (state_dir() / MARKER_FILENAME).is_file(),
    }
