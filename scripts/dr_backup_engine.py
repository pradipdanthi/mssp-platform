#!/usr/bin/env python3
"""
MSSP Disaster Recovery Backup Engine

Streams a full control-plane (+ optional remote engine) backup into an
AES-256-CBC encrypted archive on the operator USB path:

  F:\\MSSP_Full_Backup   (Windows Cursor host, typically 192.168.0.192)
  resolved on Linux as:  /mnt/mssp-dr-usb/MSSP_Full_Backup
                         or $MSSP_DR_BACKUP_ROOT

Design rules:
  - Prefer streaming into the backup root (USB/SMB mount), not the VM root disk.
  - Never print .env / secret contents.
  - Encrypt final package with openssl enc -aes-256-cbc -pbkdf2.
  - Write SHA-256 sidecar and set read-only mode on the archive.

Usage examples:
  export MSSP_DR_BACKUP_PASSPHRASE='…'   # or --passphrase-file
  python3 scripts/dr_backup_engine.py
  python3 scripts/dr_backup_engine.py --backup-root /mnt/mssp-dr-usb/MSSP_Full_Backup
  python3 scripts/dr_backup_engine.py --mount-smb   # uses MSSP_DR_SMB_* env
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WINDOWS_PATH = r"F:\MSSP_Full_Backup"
DEFAULT_SMB_HOST = "192.168.0.192"
DEFAULT_SMB_SHARE = "MSSP_Full_Backup"
DEFAULT_MOUNT_POINT = Path("/mnt/mssp-dr-usb")
DEFAULT_LINUX_RESOLVED = DEFAULT_MOUNT_POINT / "MSSP_Full_Backup"


# ---------------------------------------------------------------------------
# Topology (from ansible/inventory/hosts.yml — no secrets)
# ---------------------------------------------------------------------------

INFRASTRUCTURE: List[Dict[str, Any]] = [
    {
        "vm_id": 100,
        "hostname": "mssp-control",
        "ip": "192.168.0.201",
        "role": "control_plane",
        "services": ["postgres", "redis", "backend-api", "frontend-admin", "frontend-customer"],
        "ports": [8000, 3000, 3001],
        "compose": "/opt/mssp-control/docker-compose.yml",
        "volumes": ["postgres_data", "redis_data"],
        "ssh_key": None,  # local
    },
    {
        "vm_id": 101,
        "hostname": "wazuh-stack",
        "ip": "192.168.0.211",
        "role": "wazuh_cluster",
        "services": ["wazuh-manager", "wazuh-indexer", "wazuh-dashboard"],
        "ports": [1514, 1515, 55000, 9200, 443],
        "capture_paths": ["/var/ossec/etc", "/var/ossec/ruleset"],
        "ssh_user": "secadmin",
        "ssh_key": str(Path.home() / ".ssh/id_ed25519_wazuh_stack"),
    },
    {
        "vm_id": 102,
        "hostname": "thehive_shuffle",
        "ip": "192.168.0.212",
        "role": "case_soar",
        "services": ["thehive", "shuffle"],
        "ports": [9000, 3000],
        "capture_paths": ["/opt/shuffle", "/etc/thehive"],
        "ssh_user": "secadmin",
        "ssh_key": str(Path.home() / ".ssh/id_ed25519_case_soar"),
    },
    {
        "vm_id": 106,
        "hostname": "suricata-zeek",
        "ip": "192.168.0.216",
        "role": "network_sensors",
        "services": ["suricata", "zeek"],
        "ports": [],
        "capture_paths": ["/etc/suricata", "/opt/zeek/etc", "/opt/zeek/share/zeek"],
        "ssh_user": "secadmin",
        "ssh_key": str(Path.home() / ".ssh/id_ed25519_suricata"),
    },
    {
        "vm_id": 109,
        "hostname": "greenbone-vuln-free",
        "ip": "192.168.0.219",
        "role": "vulnerability",
        "services": ["greenbone-ce", "nuclei", "vuls"],
        "ports": [443, 9392],
        "capture_paths": ["/etc/gvm", "/opt/mssp-vuln-free", "/var/lib/gvm"],
        "ssh_user": "secadmin",
        "ssh_key": str(Path.home() / ".ssh/id_ed25519_greenbone"),
    },
]


def _log(msg: str) -> None:
    print(f"[dr-backup] {msg}", flush=True)


def _run(
    cmd: List[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    input_bytes: Optional[bytes] = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def resolve_backup_root(explicit: Optional[str]) -> Path:
    """Map F:\\MSSP_Full_Backup / env / mount candidates to a writable Path."""
    candidates: List[Path] = []
    if explicit:
        raw = explicit.strip()
        if raw.upper().startswith("F:"):
            # Windows path → Linux mount convention for Cursor host USB
            rest = raw[2:].lstrip("\\/")
            candidates.append(DEFAULT_MOUNT_POINT / rest.replace("\\", "/"))
            candidates.append(Path("/mnt/f") / rest.replace("\\", "/"))
        else:
            candidates.append(Path(raw).expanduser())
    env_root = (os.environ.get("MSSP_DR_BACKUP_ROOT") or "").strip()
    if env_root:
        candidates.append(Path(env_root).expanduser())
    candidates.extend(
        [
            DEFAULT_LINUX_RESOLVED,
            DEFAULT_MOUNT_POINT / "MSSP_Full_Backup",
            Path("/mnt/f/MSSP_Full_Backup"),
            Path("/media/MSSP_Full_Backup"),
        ]
    )
    seen = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists() and path.is_dir() and os.access(path, os.W_OK):
            return path
    # Prefer creating under an existing mount parent
    for parent, child in [
        (DEFAULT_MOUNT_POINT, "MSSP_Full_Backup"),
        (Path("/mnt/f"), "MSSP_Full_Backup"),
    ]:
        if parent.exists() and os.access(parent, os.W_OK):
            target = parent / child
            target.mkdir(parents=True, exist_ok=True)
            return target
    raise SystemExit(
        "Backup root not found / not writable.\n"
        f"Expected USB path {DEFAULT_WINDOWS_PATH} on Cursor host {DEFAULT_SMB_HOST}.\n"
        "On that Windows PC: share F:\\MSSP_Full_Backup as SMB share "
        f"'{DEFAULT_SMB_SHARE}', then on VM 100 either:\n"
        "  1) python3 scripts/dr_backup_engine.py --mount-smb\n"
        "     (set MSSP_DR_SMB_USER + MSSP_DR_SMB_PASSWORD_FILE), or\n"
        "  2) mount the share at /mnt/mssp-dr-usb and re-run, or\n"
        "  3) export MSSP_DR_BACKUP_ROOT=/path/to/writable/dir\n"
    )


def try_mount_smb(mount_point: Path) -> Path:
    """Mount //host/share to mount_point using env credentials (password from file)."""
    host = (os.environ.get("MSSP_DR_SMB_HOST") or DEFAULT_SMB_HOST).strip()
    share = (os.environ.get("MSSP_DR_SMB_SHARE") or DEFAULT_SMB_SHARE).strip()
    user = (os.environ.get("MSSP_DR_SMB_USER") or "").strip()
    pass_file = (os.environ.get("MSSP_DR_SMB_PASSWORD_FILE") or "").strip()
    domain = (os.environ.get("MSSP_DR_SMB_DOMAIN") or "").strip()

    if not user or not pass_file:
        raise SystemExit(
            "--mount-smb requires MSSP_DR_SMB_USER and MSSP_DR_SMB_PASSWORD_FILE "
            "(password file path; contents never printed)."
        )
    pf = Path(pass_file)
    if not pf.is_file():
        raise SystemExit(f"Password file not found: {pass_file}")

    password = pf.read_text(encoding="utf-8").strip("\r\n")
    if not password:
        raise SystemExit("Password file is empty.")

    mount_point.mkdir(parents=True, exist_ok=True)
    # Already mounted?
    mount_out = _run(["mount"], check=False).stdout.decode("utf-8", errors="replace")
    if str(mount_point) in mount_out and "cifs" in mount_out:
        _log(f"SMB already mounted at {mount_point}")
        return mount_point / "MSSP_Full_Backup" if (mount_point / "MSSP_Full_Backup").is_dir() else mount_point

    creds = tempfile.NamedTemporaryFile("w", delete=False, prefix="mssp-cifs-", suffix=".cred")
    try:
        creds.write(f"username={user}\npassword={password}\n")
        if domain:
            creds.write(f"domain={domain}\n")
        creds.close()
        os.chmod(creds.name, 0o600)
        unc = f"//{host}/{share}"
        cmd = [
            "sudo",
            "-n",
            "mount",
            "-t",
            "cifs",
            unc,
            str(mount_point),
            "-o",
            f"credentials={creds.name},uid={os.getuid()},gid={os.getgid()},file_mode=0640,dir_mode=0750,iocharset=utf8",
        ]
        proc = _run(cmd, check=False)
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            raise SystemExit(
                f"Failed to mount {unc} → {mount_point}.\n"
                f"Ensure the Windows share exists and sudoers allows passwordless mount.cifs.\n"
                f"Detail: {err[:400]}"
            )
        _log(f"Mounted {unc} at {mount_point}")
    finally:
        try:
            os.unlink(creds.name)
        except OSError:
            pass
        # Wipe password variable
        password = ""  # noqa: F841

    # Share root may BE the backup folder, or contain it
    nested = mount_point / "MSSP_Full_Backup"
    if nested.is_dir():
        return nested
    return mount_point


def _smb_connect() -> Tuple[str, str]:
    """Configure smbprotocol client from env; return (host, share). Never logs password."""
    try:
        import smbclient  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Python smbprotocol not installed. On VM 100 run:\n"
            "  pip3 install --user --break-system-packages smbprotocol"
        ) from exc

    host = (os.environ.get("MSSP_DR_SMB_HOST") or DEFAULT_SMB_HOST).strip()
    share = (os.environ.get("MSSP_DR_SMB_SHARE") or DEFAULT_SMB_SHARE).strip()
    user = (os.environ.get("MSSP_DR_SMB_USER") or "").strip()
    pass_file = (os.environ.get("MSSP_DR_SMB_PASSWORD_FILE") or "").strip()
    if not user or not pass_file:
        raise SystemExit(
            "SMB push requires MSSP_DR_SMB_USER and MSSP_DR_SMB_PASSWORD_FILE"
        )
    password = Path(pass_file).read_text(encoding="utf-8").strip("\r\n")
    if not password:
        raise SystemExit("SMB password file is empty.")
    smbclient.reset_connection_cache()
    smbclient.ClientConfig(username=user, password=password)
    return host, share


def smb_probe() -> None:
    """Test Windows share login; exit non-zero on failure (no secrets printed)."""
    import smbclient  # type: ignore

    host, share = _smb_connect()
    unc = fr"\\{host}\{share}"
    try:
        entries = list(smbclient.listdir(unc))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"SMB login/share failed for {unc}: {type(exc).__name__}: {str(exc)[:240]}\n"
            "On Windows 192.168.0.192:\n"
            "  1) Share F:\\MSSP_Full_Backup as share name 'MSSP_Full_Backup' (Read/Write).\n"
            "  2) Confirm password in .secrets/dr_smb_password matches that Windows user.\n"
            "  3) If using built-in Admin: enable network share access for local admins\n"
            "     (LocalAccountTokenFilterPolicy=1) OR create a normal local user for SMB.\n"
            "  4) Network profile must be Private; File and Printer Sharing enabled.\n"
        ) from exc
    _log(f"SMB OK {unc} ({len(entries)} entries)")


def smb_push_files(local_dir: Path, names: List[str]) -> None:
    """Upload named files from local_dir into \\\\host\\share via smbprotocol."""
    import smbclient  # type: ignore

    host, share = _smb_connect()
    remote_root = fr"\\{host}\{share}"
    try:
        smbclient.makedirs(remote_root, exist_ok=True)
    except Exception:
        pass
    for name in names:
        src = local_dir / name
        if not src.is_file():
            raise SystemExit(f"Missing local file to push: {src}")
        dest = fr"{remote_root}\{name}"
        _log(f"SMB upload {name} → {dest}")
        with open(src, "rb") as rf, smbclient.open_file(dest, mode="wb") as wf:
            while True:
                chunk = rf.read(1024 * 1024)
                if not chunk:
                    break
                wf.write(chunk)
    _log("SMB upload complete")


def load_passphrase(passphrase_file: Optional[str]) -> str:
    env = (os.environ.get("MSSP_DR_BACKUP_PASSPHRASE") or "").strip()
    if env:
        return env
    path = passphrase_file or os.environ.get("MSSP_DR_BACKUP_PASSPHRASE_FILE") or ""
    if path:
        p = Path(path)
        if not p.is_file():
            raise SystemExit(f"Passphrase file not found: {path}")
        val = p.read_text(encoding="utf-8").strip("\r\n")
        if not val:
            raise SystemExit("Passphrase file is empty.")
        return val
    # Auto-create a passphrase file under .secrets (gitignored) for first run
    secrets_dir = REPO_ROOT / ".secrets"
    secrets_dir.mkdir(mode=0o700, exist_ok=True)
    auto = secrets_dir / "dr_backup_passphrase"
    if not auto.exists():
        token = hashlib.sha256(os.urandom(64)).hexdigest()
        auto.write_text(token + "\n", encoding="utf-8")
        os.chmod(auto, 0o600)
        _log(f"Created passphrase file (gitignored): {auto}")
        _log("Store this file in your offline vault — required for restore.")
    return auto.read_text(encoding="utf-8").strip("\r\n")


def tcp_open(ip: str, port: int = 22, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def stream_postgres_dump(dest_sql_gz: Path) -> Dict[str, Any]:
    """Stream pg_dumpall from mssp-postgres → gzip file on backup root (no VM /tmp dump)."""
    _log("Streaming PostgreSQL pg_dumpall → gzip on backup root…")
    dest_sql_gz.parent.mkdir(parents=True, exist_ok=True)
    # Compose project assumed at REPO_ROOT
    dump = subprocess.Popen(
        [
            "docker",
            "compose",
            "-f",
            str(REPO_ROOT / "docker-compose.yml"),
            "exec",
            "-T",
            "postgres",
            "pg_dumpall",
            "-U",
            os.environ.get("POSTGRES_USER", "mssp_admin"),
        ],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert dump.stdout is not None
    with open(dest_sql_gz, "wb") as out:
        gz = subprocess.Popen(
            ["gzip", "-c"],
            stdin=dump.stdout,
            stdout=out,
            stderr=subprocess.PIPE,
        )
        dump.stdout.close()
        gz_err = gz.communicate()[1]
        dump_err = dump.communicate()[1]
    if dump.returncode not in (0, None) and dump.returncode != 0:
        raise RuntimeError(
            f"pg_dumpall failed ({dump.returncode}): "
            f"{dump_err.decode('utf-8', errors='replace')[:400]}"
        )
    if gz.returncode != 0:
        raise RuntimeError(
            f"gzip failed ({gz.returncode}): {gz_err.decode('utf-8', errors='replace')[:400]}"
        )
    size = dest_sql_gz.stat().st_size
    _log(f"PostgreSQL dump written ({size} bytes compressed)")
    return {"component": "postgres_pg_dumpall", "path": str(dest_sql_gz.name), "bytes": size}


def copy_local_vault(staging: Path) -> List[Dict[str, Any]]:
    """Copy .env + .secrets + compose/docker/nginx into staging (on backup root)."""
    items: List[Dict[str, Any]] = []
    vault = staging / "vault"
    specs = staging / "specs"
    vault.mkdir(parents=True, exist_ok=True)
    specs.mkdir(parents=True, exist_ok=True)

    env_src = REPO_ROOT / ".env"
    if env_src.is_file():
        dest = vault / "mssp-control.env"
        shutil.copy2(env_src, dest)
        os.chmod(dest, 0o600)
        items.append({"component": "env", "source": ".env", "bytes": dest.stat().st_size})
        _log("Captured control-plane .env into vault (not logged).")
    else:
        _log("WARNING: .env missing — vault will omit it.")

    secrets_src = REPO_ROOT / ".secrets"
    if secrets_src.is_dir():
        dest_sec = vault / "secrets"
        shutil.copytree(
            secrets_src,
            dest_sec,
            ignore=shutil.ignore_patterns("*.log", "__pycache__"),
            dirs_exist_ok=True,
        )
        for root, _dirs, files in os.walk(dest_sec):
            for name in files:
                os.chmod(Path(root) / name, 0o600)
        items.append({"component": "secrets_dir", "source": ".secrets", "bytes": _dir_size(dest_sec)})
        _log("Captured .secrets/ into vault (not logged).")

    for rel in [
        "docker-compose.yml",
        "backend-api/Dockerfile",
        "frontend-admin/Dockerfile",
        "frontend-customer/Dockerfile",
        "frontend-admin/nginx.conf",
        "frontend-customer/nginx.conf",
        "ansible/inventory/hosts.yml",
    ]:
        src = REPO_ROOT / rel
        if src.is_file():
            dest = specs / rel.replace("/", "__")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            items.append({"component": "spec", "source": rel, "bytes": dest.stat().st_size})

    # postgres init SQL filenames (schema inventory; data is in dump)
    init_dir = REPO_ROOT / "postgres" / "init"
    if init_dir.is_dir():
        listing = sorted(p.name for p in init_dir.glob("*.sql"))
        (specs / "postgres_init_file_list.json").write_text(
            json.dumps(listing, indent=2) + "\n", encoding="utf-8"
        )
        items.append({"component": "schema_file_list", "count": len(listing)})

    # systemd units if any local
    systemd_out = specs / "systemd"
    systemd_out.mkdir(exist_ok=True)
    for unit in Path("/etc/systemd/system").glob("mssp*.service"):
        shutil.copy2(unit, systemd_out / unit.name)
        items.append({"component": "systemd", "source": str(unit)})

    return items


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def stream_remote_capture(staging: Path, node: Dict[str, Any]) -> Dict[str, Any]:
    """SSH tar of capture_paths streamed into staging on backup root (no remote temp archive)."""
    import shlex

    ip = node["ip"]
    result: Dict[str, Any] = {
        "vm_id": node.get("vm_id"),
        "hostname": node.get("hostname"),
        "ip": ip,
        "status": "skipped",
    }
    if node.get("vm_id") == 100:
        result["status"] = "local"
        return result
    key = node.get("ssh_key")
    user = node.get("ssh_user") or "secadmin"
    paths = [p for p in (node.get("capture_paths") or []) if p]
    if not key or not Path(key).is_file():
        result["status"] = "no_ssh_key"
        return result
    if not tcp_open(ip, 22):
        result["status"] = "ssh_unreachable"
        return result
    if not paths:
        result["status"] = "no_paths"
        return result

    # Build a safe remote bash snippet (no nested quote breakage).
    path_checks = " ".join(
        f"[ -e {shlex.quote(p)} ] && set -- \"$@\" {shlex.quote(p)};" for p in paths
    )
    remote_script = (
        "set --; "
        + path_checks
        + ' if [ "$#" -eq 0 ]; then echo NO_PATHS >&2; exit 2; fi; '
        "tar -czf - \"$@\""
    )
    out_file = staging / "remote" / f"vm{node['vm_id']}_{node['hostname']}.tar.gz"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    _log(f"Streaming remote config from {ip} (VM {node.get('vm_id')})…")
    with open(out_file, "wb") as out:
        proc = subprocess.run(
            [
                "ssh",
                "-i",
                key,
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "ConnectTimeout=8",
                f"{user}@{ip}",
                "bash",
                "-lc",
                remote_script,
            ],
            stdout=out,
            stderr=subprocess.PIPE,
            check=False,
        )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")[:300]
        try:
            out_file.unlink(missing_ok=True)
        except OSError:
            pass
        result["status"] = "capture_failed"
        result["error"] = err
        _log(f"Remote capture failed for {ip}: {err}")
        return result
    result["status"] = "ok"
    result["bytes"] = out_file.stat().st_size
    result["archive"] = out_file.name
    return result


def build_manifest(
    backup_root: Path,
    archive_name: str,
    sha256: str,
    components: List[Dict[str, Any]],
    remote_results: List[Dict[str, Any]],
) -> Path:
    git_head = ""
    try:
        git_head = (
            _run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT)
            .stdout.decode()
            .strip()
        )
    except Exception:  # noqa: BLE001
        git_head = "unknown"

    nodes = []
    for n in INFRASTRUCTURE:
        entry = {
            "vm_id": n["vm_id"],
            "hostname": n["hostname"],
            "ip": n["ip"],
            "role": n["role"],
            "services": n.get("services"),
            "ports": n.get("ports"),
            "compose": n.get("compose"),
            "volumes": n.get("volumes"),
            "ssh_reachable": tcp_open(n["ip"], 22) if n["vm_id"] != 100 else True,
        }
        nodes.append(entry)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backup_root_windows": DEFAULT_WINDOWS_PATH,
        "backup_root_resolved": str(backup_root),
        "cursor_usb_host": DEFAULT_SMB_HOST,
        "control_plane_repo": str(REPO_ROOT),
        "git_head": git_head,
        "encrypted_archive": archive_name,
        "sha256": sha256,
        "encryption": "openssl enc -aes-256-cbc -pbkdf2",
        "nodes": nodes,
        "components": components,
        "remote_captures": remote_results,
        "ports_summary": {
            "admin_portal": "http://192.168.0.201:3000",
            "customer_portal": "http://192.168.0.201:3001",
            "api": "http://192.168.0.201:8000",
        },
    }
    path = backup_root / "infrastructure_manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _log(f"Wrote {path}")
    return path


def pack_and_encrypt(
    staging: Path,
    backup_root: Path,
    passphrase: str,
    timestamp: str,
) -> Tuple[Path, str]:
    """tar staging → gzip stream → openssl AES-256-CBC; write .sha256; chmod read-only."""
    archive_name = f"MSSP_FULL_STACK_BACKUP_{timestamp}.sql.gz.enc"
    archive_path = backup_root / archive_name
    sha_path = backup_root / f"{archive_name}.sha256"

    _log(f"Encrypting package → {archive_name}")
    # tar czf - staging | openssl enc ...
    tar = subprocess.Popen(
        ["tar", "-C", str(staging), "-czf", "-", "."],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert tar.stdout is not None
    pass_env = os.environ.copy()
    # Use file descriptor style via -pass env: to avoid argv exposure in `ps`
    pass_env["MSSP_DR_OPENSSL_PASS"] = passphrase
    enc = subprocess.Popen(
        [
            "openssl",
            "enc",
            "-aes-256-cbc",
            "-pbkdf2",
            "-salt",
            "-pass",
            "env:MSSP_DR_OPENSSL_PASS",
        ],
        stdin=tar.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=pass_env,
    )
    tar.stdout.close()
    assert enc.stdout is not None

    h = hashlib.sha256()
    with open(archive_path, "wb") as out:
        while True:
            chunk = enc.stdout.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            out.write(chunk)
    tar.wait()
    enc_err = enc.communicate()[1]
    if tar.returncode != 0:
        raise RuntimeError(f"tar failed: {tar.stderr.read().decode('utf-8', errors='replace')[:400]}")
    if enc.returncode != 0:
        raise RuntimeError(f"openssl enc failed: {enc_err.decode('utf-8', errors='replace')[:400]}")

    digest = h.hexdigest()
    sha_path.write_text(f"{digest}  {archive_name}\n", encoding="utf-8")

    # Immutability: owner read-only
    os.chmod(archive_path, 0o440)
    os.chmod(sha_path, 0o440)
    # Best-effort chattr +i if available (may need root)
    _run(["chattr", "+i", str(archive_path)], check=False)

    _log(f"Archive ready: {archive_path} ({archive_path.stat().st_size} bytes)")
    _log(f"SHA-256: {digest}")
    return archive_path, digest


def main() -> int:
    parser = argparse.ArgumentParser(description="MSSP full-stack DR backup engine")
    parser.add_argument(
        "--backup-root",
        default=os.environ.get("MSSP_DR_BACKUP_ROOT") or DEFAULT_WINDOWS_PATH,
        help=f"Destination root (default: {DEFAULT_WINDOWS_PATH} → Linux mount)",
    )
    parser.add_argument(
        "--mount-smb",
        action="store_true",
        help=f"Mount //{DEFAULT_SMB_HOST}/{DEFAULT_SMB_SHARE} before backup (needs mount.cifs + sudo)",
    )
    parser.add_argument(
        "--smb-push",
        action="store_true",
        help=(
            f"After creating the archive locally, upload it to "
            f"//{DEFAULT_SMB_HOST}/{DEFAULT_SMB_SHARE} via smbprotocol (no root required)"
        ),
    )
    parser.add_argument(
        "--smb-probe",
        action="store_true",
        help="Only test SMB login to the Windows USB share, then exit",
    )
    parser.add_argument("--passphrase-file", default=None, help="AES passphrase file path")
    parser.add_argument(
        "--skip-remote",
        action="store_true",
        help="Only back up VM 100 control plane (skip SSH to 101/102/106/109)",
    )
    parser.add_argument(
        "--keep-staging",
        action="store_true",
        help="Keep unencrypted staging dir on backup root (debug only)",
    )
    args = parser.parse_args()

    if args.smb_probe:
        smb_probe()
        return 0

    if args.mount_smb:
        backup_root = try_mount_smb(DEFAULT_MOUNT_POINT)
        # If share root is the backup folder itself
        if backup_root.name != "MSSP_Full_Backup":
            nested = backup_root / "MSSP_Full_Backup"
            nested.mkdir(parents=True, exist_ok=True)
            backup_root = nested
    elif args.smb_push:
        # Build on local mirror, then push encrypted outputs to Windows USB share
        backup_root = Path(
            os.environ.get("MSSP_DR_BACKUP_ROOT")
            or str(Path.home() / "MSSP_Full_Backup")
        )
        backup_root.mkdir(parents=True, exist_ok=True)
    else:
        backup_root = resolve_backup_root(args.backup_root)

    _log(f"Backup root: {backup_root}")
    passphrase = load_passphrase(args.passphrase_file)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    staging = backup_root / f".staging_{timestamp}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        components: List[Dict[str, Any]] = []
        components.append(stream_postgres_dump(staging / "postgres" / "pg_dumpall.sql.gz"))
        components.extend(copy_local_vault(staging))

        remote_results: List[Dict[str, Any]] = []
        for node in INFRASTRUCTURE:
            if args.skip_remote and node.get("vm_id") != 100:
                remote_results.append(
                    {
                        "vm_id": node.get("vm_id"),
                        "ip": node.get("ip"),
                        "status": "skipped_by_flag",
                    }
                )
                continue
            remote_results.append(stream_remote_capture(staging, node))

        meta = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "repo": str(REPO_ROOT),
            "engine": "scripts/dr_backup_engine.py",
        }
        (staging / "BACKUP_META.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

        archive_path, digest = pack_and_encrypt(staging, backup_root, passphrase, timestamp)
        build_manifest(
            backup_root,
            archive_path.name,
            digest,
            components,
            remote_results,
        )

        # Latest pointer (mutable ok)
        latest = backup_root / "LATEST_BACKUP.txt"
        latest.write_text(archive_path.name + "\n", encoding="utf-8")

        if args.smb_push:
            smb_probe()
            smb_push_files(
                backup_root,
                [
                    archive_path.name,
                    f"{archive_path.name}.sha256",
                    "infrastructure_manifest.json",
                    "LATEST_BACKUP.txt",
                ],
            )

        _log("SUCCESS")
        _log(f"Encrypted archive: {archive_path}")
        _log(f"Checksum file:     {archive_path}.sha256")
        _log(f"Manifest:          {backup_root / 'infrastructure_manifest.json'}")
        if args.smb_push:
            _log(f"Also uploaded to //{DEFAULT_SMB_HOST}/{DEFAULT_SMB_SHARE}")
        return 0
    finally:
        # Always wipe passphrase from env copy references
        if "MSSP_DR_OPENSSL_PASS" in os.environ:
            os.environ.pop("MSSP_DR_OPENSSL_PASS", None)
        if not args.keep_staging and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        _log("Interrupted")
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        _log(f"FAILED: {exc}")
        sys.exit(1)
