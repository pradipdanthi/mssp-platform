#!/usr/bin/env python3
"""
MSSP Disaster Recovery Backup Engine (complete stack)

Streams control-plane + engine-VM config/state into an AES-256-CBC archive
and uploads to the operator USB share:

  F:\\MSSP_Full_Backup  →  \\\\192.168.0.192\\MSSP_Full_Backup
  Windows account Name: User  (Full Name may show as Admin)

Design:
  - Prefer writing/staging on backup root or home mirror (not /tmp).
  - Never print .env / secret values.
  - openssl enc -aes-256-cbc -pbkdf2; SHA-256 sidecar; mode 440.
  - Remote captures use sudo tar over SSH (no remote temp archives).
  - Large regenerable feed DBs are inventoried as intentional skips unless
    --include-heavy-feeds is set (Greenbone scap/psql/vt/notus, Vuls DB).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WINDOWS_PATH = r"F:\MSSP_Full_Backup"
DEFAULT_SMB_HOST = "192.168.0.192"
DEFAULT_SMB_SHARE = "MSSP_Full_Backup"
DEFAULT_MOUNT_POINT = Path("/mnt/mssp-dr-usb")
DEFAULT_LINUX_RESOLVED = DEFAULT_MOUNT_POINT / "MSSP_Full_Backup"

# Critical remote nodes must succeed for a "complete" backup.
# VM 112 (Ansible automation controller) is required for post-restore operations.
CRITICAL_REMOTE_VM_IDS = {101, 102, 106, 108, 109, 110, 112}

INFRASTRUCTURE: List[Dict[str, Any]] = [
    {
        "vm_id": 100,
        "hostname": "mssp-control",
        "ip": "192.168.0.201",
        "role": "control_plane",
        "services": ["postgres", "redis", "backend-api", "frontend-admin", "frontend-customer"],
        "ports": [8000, 3000, 3001],
        "compose": "/opt/mssp-control/docker-compose.yml",
        "volumes": ["mssp-control_postgres_data", "mssp-control_redis_data"],
        "ssh_key": None,
    },
    {
        "vm_id": 101,
        "hostname": "wazuh-stack",
        "ip": "192.168.0.211",
        "role": "wazuh_cluster",
        "services": ["wazuh-manager", "wazuh-indexer", "wazuh-dashboard"],
        "ports": [1514, 1515, 55000, 9200, 443],
        "ssh_user": "secadmin",
        "ssh_key": str(Path.home() / ".ssh/id_ed25519_wazuh_stack"),
        "use_sudo": True,
        "capture_paths": [
            "/var/ossec/etc",
            "/var/ossec/ruleset",
            "/var/ossec/integrations",
            "/var/ossec/agentless",
            "/etc/wazuh-indexer",
            "/etc/wazuh-dashboard",
        ],
        "exclude_globs": ["*/queue/*", "*/logs/*", "*/var/run/*"],
    },
    {
        "vm_id": 102,
        "hostname": "thehive_shuffle",
        "ip": "192.168.0.212",
        "role": "case_soar",
        "services": ["thehive", "shuffle"],
        "ports": [9000, 3000],
        "ssh_user": "secadmin",
        "ssh_key": str(Path.home() / ".ssh/id_ed25519_case_soar"),
        "use_sudo": True,
        "capture_paths": ["/opt/mssp-case-soar"],
        "docker_volumes": [
            "thehive_thehive-data",
            "thehive_thehive-cass-data",
            "src_shuffle-database",
        ],
    },
    {
        "vm_id": 106,
        "hostname": "suricata-zeek",
        "ip": "192.168.0.216",
        "role": "network_sensors",
        "services": ["suricata", "zeek", "wazuh-agent"],
        "ports": [],
        "ssh_user": "secadmin",
        "ssh_key": str(Path.home() / ".ssh/id_ed25519_suricata"),
        "use_sudo": True,
        "capture_paths": [
            "/etc/suricata",
            "/var/ossec/etc",
            "/opt/zeek-logs",
        ],
        # suricata rules/state under /var/lib/suricata can be large; keep configs + rules only
        "extra_tar_args": [],
    },
    {
        "vm_id": 108,
        "hostname": "misp",
        "ip": "192.168.0.218",
        "role": "threat_intel",
        "services": ["misp_rest_bridge"],
        "ports": [8080],
        "ssh_user": "secadmin",
        "ssh_key": str(Path.home() / ".ssh/id_ed25519_misp"),
        "use_sudo": True,
        "capture_paths": [
            "/opt/mssp-misp",
        ],
    },
    {
        "vm_id": 109,
        "hostname": "greenbone-vuln-free",
        "ip": "192.168.0.219",
        "role": "vulnerability",
        "services": ["greenbone-ce", "nuclei", "vuls", "amass_easm"],
        "ports": [443, 9392],
        "ssh_user": "secadmin",
        "ssh_key": str(Path.home() / ".ssh/id_ed25519_greenbone"),
        "use_sudo": True,
        "capture_paths": [
            "/opt/mssp-greenbone/community",
            "/opt/mssp-vuln-free/secrets",
            "/opt/mssp-vuln-free/bin",
            "/opt/mssp-easm-agent",
        ],
        "docker_volumes_light": [
            "greenbone-community-edition_nginx_config_vol",
            "greenbone-community-edition_nginx_certificates_vol",
            "greenbone-community-edition_cert_data_vol",
            "greenbone-community-edition_gpg_data_vol",
            "greenbone-community-edition_gvmd_data_vol",
            "greenbone-community-edition_gsa_data_vol",
            "greenbone-community-edition_data_objects_vol",
        ],
        "docker_volumes_heavy": [
            "greenbone-community-edition_psql_data_vol",
            "greenbone-community-edition_scap_data_vol",
            "greenbone-community-edition_vt_data_vol",
            "greenbone-community-edition_notus_data_vol",
        ],
        "heavy_paths_optional": [
            "/opt/mssp-vuln-free/vuls",
            "/opt/mssp-vuln-free/nuclei-templates",
        ],
    },
    {
        "vm_id": 110,
        "hostname": "velociraptor",
        "ip": "192.168.0.220",
        "role": "dfir",
        "services": ["velociraptor", "mssp_velociraptor_bridge"],
        "ports": [8000, 8001, 8002, 8889],
        "ssh_user": "secadmin",
        "ssh_key": str(Path.home() / ".ssh/id_ed25519_velociraptor"),
        "use_sudo": True,
        "capture_paths": [
            "/etc/velociraptor",
            "/opt/mssp-velociraptor",
        ],
        "exclude_globs": ["*/clients/*/collections/*", "*/filestore/*"],
    },
    {
        "vm_id": 112,
        "hostname": "automation",
        "ip": "192.168.0.222",
        "role": "ansible_controller",
        "services": ["ansible"],
        "ports": [22],
        "ssh_user": "secadmin",
        "ssh_key": str(Path.home() / ".ssh/id_ed25519_automation"),
        "use_sudo": False,
        # Tree + controller SSH keys used to reach engine VMs after restore
        "capture_paths": [
            "/home/secadmin/mssp-automation",
            "/home/secadmin/.ssh",
            "/home/secadmin/.ansible",
        ],
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
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def resolve_backup_root(explicit: Optional[str]) -> Path:
    candidates: List[Path] = []
    if explicit:
        raw = explicit.strip()
        if raw.upper().startswith("F:"):
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
            Path.home() / "MSSP_Full_Backup",
        ]
    )
    for path in candidates:
        if path.exists() and path.is_dir() and os.access(path, os.W_OK):
            return path
        try:
            path.mkdir(parents=True, exist_ok=True)
            if os.access(path, os.W_OK):
                return path
        except OSError:
            continue
    raise SystemExit(
        "Backup root not writable. Set MSSP_DR_BACKUP_ROOT or use --smb-push "
        f"(USB host {DEFAULT_SMB_HOST}, share {DEFAULT_SMB_SHARE}, user User)."
    )


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
    secrets_dir = REPO_ROOT / ".secrets"
    secrets_dir.mkdir(mode=0o700, exist_ok=True)
    auto = secrets_dir / "dr_backup_passphrase"
    if not auto.exists():
        token = hashlib.sha256(os.urandom(64)).hexdigest()
        auto.write_text(token + "\n", encoding="utf-8")
        os.chmod(auto, 0o600)
        _log(f"Created passphrase file (gitignored): {auto}")
    return auto.read_text(encoding="utf-8").strip("\r\n")


def tcp_open(ip: str, port: int = 22, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _smb_connect() -> Tuple[str, str]:
    try:
        import smbclient  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Install smbprotocol: pip3 install --user --break-system-packages smbprotocol"
        ) from exc
    host = (os.environ.get("MSSP_DR_SMB_HOST") or DEFAULT_SMB_HOST).strip()
    share = (os.environ.get("MSSP_DR_SMB_SHARE") or DEFAULT_SMB_SHARE).strip()
    user = (os.environ.get("MSSP_DR_SMB_USER") or "User").strip()
    pass_file = (
        os.environ.get("MSSP_DR_SMB_PASSWORD_FILE")
        or str(REPO_ROOT / ".secrets" / "dr_smb_password")
    ).strip()
    password = Path(pass_file).read_text(encoding="utf-8").strip("\r\n")
    if not password:
        raise SystemExit("SMB password file is empty.")
    smbclient.reset_connection_cache()
    smbclient.ClientConfig(username=user, password=password)
    return host, share


def smb_probe() -> None:
    import smbclient  # type: ignore

    host, share = _smb_connect()
    unc = fr"\\{host}\{share}"
    try:
        entries = list(smbclient.listdir(unc))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"SMB failed for {unc}: {type(exc).__name__}: {str(exc)[:240]}") from exc
    _log(f"SMB OK {unc} ({len(entries)} entries)")


def smb_push_files(local_dir: Path, names: List[str]) -> None:
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
        _log(f"SMB upload {name}")
        with open(src, "rb") as rf, smbclient.open_file(dest, mode="wb") as wf:
            while True:
                chunk = rf.read(1024 * 1024)
                if not chunk:
                    break
                wf.write(chunk)
    _log("SMB upload complete")


def stream_postgres_dump(dest_sql_gz: Path) -> Dict[str, Any]:
    _log("Streaming PostgreSQL pg_dumpall → gzip…")
    dest_sql_gz.parent.mkdir(parents=True, exist_ok=True)
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
        gz = subprocess.Popen(["gzip", "-c"], stdin=dump.stdout, stdout=out, stderr=subprocess.PIPE)
        dump.stdout.close()
        gz_err = gz.communicate()[1]
        dump_err = dump.communicate()[1]
    if dump.returncode not in (0, None) and dump.returncode != 0:
        raise RuntimeError(f"pg_dumpall failed: {dump_err.decode('utf-8', errors='replace')[:400]}")
    if gz.returncode != 0:
        raise RuntimeError(f"gzip failed: {gz_err.decode('utf-8', errors='replace')[:400]}")
    size = dest_sql_gz.stat().st_size
    if size < 1000:
        raise RuntimeError(f"pg_dumpall output too small ({size} bytes) — aborting")
    _log(f"PostgreSQL dump OK ({size} bytes compressed)")
    return {"component": "postgres_pg_dumpall", "path": dest_sql_gz.name, "bytes": size}


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def copy_local_vault(staging: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    vault = staging / "vault"
    specs = staging / "specs"
    schema = staging / "schema"
    vault.mkdir(parents=True, exist_ok=True)
    specs.mkdir(parents=True, exist_ok=True)
    schema.mkdir(parents=True, exist_ok=True)

    env_src = REPO_ROOT / ".env"
    if not env_src.is_file():
        raise RuntimeError("Control-plane .env missing — cannot produce complete backup")
    dest = vault / "mssp-control.env"
    shutil.copy2(env_src, dest)
    os.chmod(dest, 0o600)
    items.append({"component": "env", "bytes": dest.stat().st_size})
    _log("Captured .env")

    secrets_src = REPO_ROOT / ".secrets"
    if not secrets_src.is_dir():
        raise RuntimeError(".secrets/ missing — cannot produce complete backup")
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
    items.append({"component": "secrets_dir", "bytes": _dir_size(dest_sec)})
    _log("Captured .secrets/")

    required_specs = [
        "docker-compose.yml",
        "backend-api/Dockerfile",
        "backend-api/requirements.txt",
        "frontend-admin/Dockerfile",
        "frontend-admin/nginx.conf",
        "frontend-customer/Dockerfile",
        "frontend-customer/nginx.conf",
        "ansible/inventory/hosts.yml",
        "DOCS/DISASTER_RECOVERY_PLAYBOOK.md",
        "DOCS/CURSOR_REDEPLOYMENT_PLAYBOOK.md",
    ]
    for rel in required_specs:
        src = REPO_ROOT / rel
        if not src.is_file():
            raise RuntimeError(f"Required spec missing: {rel}")
        dest_f = specs / rel.replace("/", "__")
        shutil.copy2(src, dest_f)
        items.append({"component": "spec", "source": rel, "bytes": dest_f.stat().st_size})

    init_dir = REPO_ROOT / "postgres" / "init"
    sql_files = sorted(init_dir.glob("*.sql"))
    if len(sql_files) < 27:
        raise RuntimeError(f"Expected >=27 postgres init SQL files, found {len(sql_files)}")
    for sql in sql_files:
        shutil.copy2(sql, schema / sql.name)
    items.append({"component": "schema_sql_files", "count": len(sql_files)})
    _log(f"Captured {len(sql_files)} postgres/init SQL files")

    # Git pin
    head = _run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=False)
    branch = _run(["git", "branch", "--show-current"], cwd=REPO_ROOT, check=False)
    (specs / "git_pin.json").write_text(
        json.dumps(
            {
                "head": head.stdout.decode().strip() if head.returncode == 0 else None,
                "branch": branch.stdout.decode().strip() if branch.returncode == 0 else None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Local docker inventory
    ps = _run(["docker", "compose", "ps", "--format", "json"], cwd=REPO_ROOT, check=False)
    (specs / "docker_compose_ps.json").write_bytes(ps.stdout or b"[]")
    vols = _run(["docker", "volume", "ls", "--format", "{{.Name}}"], check=False)
    (specs / "docker_volumes.txt").write_bytes(vols.stdout or b"")

    systemd_out = specs / "systemd"
    systemd_out.mkdir(exist_ok=True)
    for unit in Path("/etc/systemd/system").glob("mssp*.service"):
        shutil.copy2(unit, systemd_out / unit.name)
        items.append({"component": "systemd", "source": str(unit)})

    return items


def stream_remote_capture(
    staging: Path,
    node: Dict[str, Any],
    *,
    include_heavy_feeds: bool,
) -> Dict[str, Any]:
    ip = node["ip"]
    result: Dict[str, Any] = {
        "vm_id": node.get("vm_id"),
        "hostname": node.get("hostname"),
        "ip": ip,
        "status": "skipped",
        "skipped_heavy": [],
    }
    if node.get("vm_id") == 100:
        result["status"] = "local"
        return result

    key = node.get("ssh_key")
    user = node.get("ssh_user") or "secadmin"
    paths = list(node.get("capture_paths") or [])
    if include_heavy_feeds:
        paths.extend(node.get("heavy_paths_optional") or [])
    else:
        for p in node.get("heavy_paths_optional") or []:
            result["skipped_heavy"].append({"path": p, "reason": "regenerable_feed_db"})

    if not key or not Path(key).is_file():
        result["status"] = "no_ssh_key"
        return result
    if not tcp_open(ip, 22):
        result["status"] = "ssh_unreachable"
        return result
    if not paths and not node.get("docker_volumes") and not node.get("docker_volumes_light"):
        result["status"] = "no_paths"
        return result

    out_file = staging / "remote" / f"vm{node['vm_id']}_{node['hostname']}.tar.gz"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    _log(f"Streaming remote capture from {ip} (VM {node.get('vm_id')})…")

    sudo = "sudo -n " if node.get("use_sudo") else ""
    # Build remote script: collect existing paths (test with sudo when needed)
    excludes = node.get("exclude_globs") or []
    excl_flags = " ".join(f"--exclude={shlex.quote(x)}" for x in excludes)
    test_bin = "sudo -n test" if node.get("use_sudo") else "test"
    # Avoid `set -- "$@"` here: on some hosts a bare/misparsed `set` dumps the
    # environment to stdout and corrupts the tar.gz stream.
    path_append = " ".join(
        f'{test_bin} -e {shlex.quote(p)} && paths="$paths {shlex.quote(p)}";' for p in paths
    )

    # Docker volume tarballs appended into same stream via temporary dirs on remote? 
    # Better: separate volume archives streamed in a second SSH to keep scripts simple.
    remote_script = (
        "set -e; paths=; "
        + path_append
        + ' if [ -z "$paths" ]; then echo NO_PATHS >&2; exit 2; fi; '
        f"{sudo}tar -czf - {excl_flags} $paths"
    )

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
                "ConnectTimeout=12",
                f"{user}@{ip}",
                # ssh joins argv with spaces — quote the entire -c payload
                f"bash --noprofile --norc -c {shlex.quote(remote_script)}",
            ],
            stdout=out,
            stderr=subprocess.PIPE,
            check=False,
        )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")[:400]
        out_file.unlink(missing_ok=True)
        result["status"] = "capture_failed"
        result["error"] = err
        _log(f"Remote path capture FAILED for {ip}: {err}")
        return result

    result["bytes"] = out_file.stat().st_size
    result["archive"] = out_file.name
    if result["bytes"] < 100:
        result["status"] = "capture_empty"
        _log(f"Remote capture suspiciously small for {ip}")
        return result
    # Reject corrupted captures (e.g. shell `set` env dump mixed into stdout)
    with open(out_file, "rb") as fh:
        magic = fh.read(2)
    if magic != b"\x1f\x8b":
        out_file.unlink(missing_ok=True)
        result["status"] = "capture_corrupt"
        result["error"] = f"expected gzip magic, got {magic!r}"
        _log(f"Remote path capture CORRUPT for {ip}: {result['error']}")
        return result

    # Docker volumes (light always; heavy only with flag)
    vol_names = list(node.get("docker_volumes") or []) + list(node.get("docker_volumes_light") or [])
    heavy = list(node.get("docker_volumes_heavy") or [])
    if include_heavy_feeds:
        vol_names.extend(heavy)
    else:
        for v in heavy:
            result["skipped_heavy"].append({"volume": v, "reason": "large_regenerable_feed"})

    vol_dir = staging / "remote" / f"vm{node['vm_id']}_volumes"
    vol_dir.mkdir(parents=True, exist_ok=True)
    vol_ok = []
    for vol in vol_names:
        vol_out = vol_dir / f"{vol}.tar.gz"
        _log(f"  volume {vol} from {ip}…")
        # Stream volume via alpine helper on remote (needs sudo docker)
        remote_vol = (
            f"set -e; "
            f"sudo -n docker volume inspect {shlex.quote(vol)} >/dev/null; "
            f"sudo -n docker run --rm -v {shlex.quote(vol)}:/data:ro alpine:3.20 "
            f"tar -czf - -C /data ."
        )
        with open(vol_out, "wb") as out:
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
                    "ConnectTimeout=12",
                    f"{user}@{ip}",
                    f"bash --noprofile --norc -c {shlex.quote(remote_vol)}",
                ],
                stdout=out,
                stderr=subprocess.PIPE,
                check=False,
            )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")[:300]
            vol_out.unlink(missing_ok=True)
            result["status"] = "volume_capture_failed"
            result["error"] = f"{vol}: {err}"
            _log(f"Volume capture FAILED {ip}/{vol}: {err}")
            return result
        vol_ok.append({"volume": vol, "bytes": vol_out.stat().st_size})

    result["volumes"] = vol_ok
    result["status"] = "ok"
    _log(f"Remote OK {ip}: paths={result['bytes']} bytes, volumes={len(vol_ok)}")
    return result


def build_manifest(
    backup_root: Path,
    archive_name: str,
    sha256: str,
    components: List[Dict[str, Any]],
    remote_results: List[Dict[str, Any]],
    include_heavy_feeds: bool,
) -> Path:
    git_head = ""
    try:
        git_head = _run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).stdout.decode().strip()
    except Exception:  # noqa: BLE001
        git_head = "unknown"

    nodes = []
    for n in INFRASTRUCTURE:
        nodes.append(
            {
                "vm_id": n["vm_id"],
                "hostname": n["hostname"],
                "ip": n["ip"],
                "role": n["role"],
                "services": n.get("services"),
                "ports": n.get("ports"),
                "compose": n.get("compose"),
                "volumes": n.get("volumes"),
                "ssh_reachable": True if n["vm_id"] == 100 else tcp_open(n["ip"], 22),
            }
        )

    failures = [r for r in remote_results if r.get("vm_id") in CRITICAL_REMOTE_VM_IDS and r.get("status") != "ok"]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backup_root_windows": DEFAULT_WINDOWS_PATH,
        "backup_root_resolved": str(backup_root),
        "cursor_usb_host": DEFAULT_SMB_HOST,
        "smb_share": DEFAULT_SMB_SHARE,
        "smb_user": "User",
        "control_plane_repo": str(REPO_ROOT),
        "git_head": git_head,
        "encrypted_archive": archive_name,
        "sha256": sha256,
        "encryption": "openssl enc -aes-256-cbc -pbkdf2",
        "include_heavy_feeds": include_heavy_feeds,
        "complete": len(failures) == 0,
        "critical_remote_failures": failures,
        "nodes": nodes,
        "components": components,
        "remote_captures": remote_results,
        "ports_summary": {
            "admin_portal": "http://192.168.0.201:3000",
            "customer_portal": "http://192.168.0.201:3001",
            "api": "http://192.168.0.201:8000",
        },
        "intentional_skips_note": (
            "Heavy Greenbone feed/DB volumes and Vuls/Nuclei template trees are skipped "
            "by default (regenerable). Re-run with --include-heavy-feeds for full bit copies."
        ),
    }
    path = backup_root / "infrastructure_manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _log(f"Wrote {path} complete={manifest['complete']}")
    return path


def pack_and_encrypt(
    staging: Path,
    backup_root: Path,
    passphrase: str,
    timestamp: str,
) -> Tuple[Path, str]:
    archive_name = f"MSSP_FULL_STACK_BACKUP_{timestamp}.sql.gz.enc"
    archive_path = backup_root / archive_name
    sha_path = backup_root / f"{archive_name}.sha256"
    _log(f"Encrypting package → {archive_name}")

    tar = subprocess.Popen(
        ["tar", "-C", str(staging), "-czf", "-", "."],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert tar.stdout is not None
    pass_env = os.environ.copy()
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
        raise RuntimeError("tar failed while packing staging")
    if enc.returncode != 0:
        raise RuntimeError(f"openssl enc failed: {enc_err.decode('utf-8', errors='replace')[:400]}")

    digest = h.hexdigest()
    sha_path.write_text(f"{digest}  {archive_name}\n", encoding="utf-8")
    os.chmod(archive_path, 0o440)
    os.chmod(sha_path, 0o440)
    _run(["chattr", "+i", str(archive_path)], check=False)
    _log(f"Archive ready ({archive_path.stat().st_size} bytes) sha256={digest}")
    return archive_path, digest


def verify_archive_inventory(staging: Path, remote_results: List[Dict[str, Any]]) -> List[str]:
    """Return list of gap descriptions; empty means OK."""
    gaps: List[str] = []
    if not (staging / "postgres" / "pg_dumpall.sql.gz").is_file():
        gaps.append("missing postgres dump")
    if not (staging / "vault" / "mssp-control.env").is_file():
        gaps.append("missing .env vault")
    if not (staging / "vault" / "secrets").is_dir():
        gaps.append("missing secrets vault")
    sql_n = len(list((staging / "schema").glob("*.sql"))) if (staging / "schema").is_dir() else 0
    if sql_n < 27:
        gaps.append(f"schema SQL count {sql_n} < 27")
    for r in remote_results:
        if r.get("vm_id") in CRITICAL_REMOTE_VM_IDS and r.get("status") != "ok":
            gaps.append(f"VM {r.get('vm_id')} {r.get('ip')} status={r.get('status')} err={r.get('error')}")
    return gaps


def main() -> int:
    parser = argparse.ArgumentParser(description="MSSP complete DR backup engine")
    parser.add_argument("--backup-root", default=os.environ.get("MSSP_DR_BACKUP_ROOT") or DEFAULT_WINDOWS_PATH)
    parser.add_argument("--smb-push", action="store_true", help="Upload archive to Windows USB share")
    parser.add_argument("--smb-probe", action="store_true", help="Test SMB only")
    parser.add_argument("--passphrase-file", default=None)
    parser.add_argument("--skip-remote", action="store_true")
    parser.add_argument(
        "--include-heavy-feeds",
        action="store_true",
        help="Also copy large Greenbone/Vuls/Nuclei feed data (multi-GB)",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Do not abort if a critical remote capture fails (NOT recommended)",
    )
    parser.add_argument("--keep-staging", action="store_true")
    args = parser.parse_args()

    # Default env for this lab USB host
    os.environ.setdefault("MSSP_DR_SMB_USER", "User")
    os.environ.setdefault(
        "MSSP_DR_SMB_PASSWORD_FILE", str(REPO_ROOT / ".secrets" / "dr_smb_password")
    )
    os.environ.setdefault("MSSP_DR_SMB_HOST", DEFAULT_SMB_HOST)
    os.environ.setdefault("MSSP_DR_SMB_SHARE", DEFAULT_SMB_SHARE)

    if args.smb_probe:
        smb_probe()
        return 0

    if args.smb_push:
        backup_root = Path(os.environ.get("MSSP_DR_BACKUP_ROOT") or (Path.home() / "MSSP_Full_Backup"))
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
                    {"vm_id": node.get("vm_id"), "ip": node.get("ip"), "status": "skipped_by_flag"}
                )
                continue
            remote_results.append(
                stream_remote_capture(
                    staging, node, include_heavy_feeds=args.include_heavy_feeds
                )
            )

        gaps = verify_archive_inventory(staging, remote_results)
        if gaps and not args.allow_partial:
            raise RuntimeError("Backup incomplete — gaps: " + "; ".join(gaps))
        if gaps:
            _log("WARNING partial backup gaps: " + "; ".join(gaps))

        meta = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "repo": str(REPO_ROOT),
            "engine": "scripts/dr_backup_engine.py",
            "include_heavy_feeds": args.include_heavy_feeds,
            "gaps": gaps,
        }
        (staging / "BACKUP_META.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

        # Inventory file listing for restore verification
        listing = []
        for root, _dirs, files in os.walk(staging):
            for name in files:
                p = Path(root) / name
                listing.append(
                    {
                        "path": str(p.relative_to(staging)),
                        "bytes": p.stat().st_size,
                    }
                )
        (staging / "CONTENT_INVENTORY.json").write_text(
            json.dumps(listing, indent=2) + "\n", encoding="utf-8"
        )

        archive_path, digest = pack_and_encrypt(staging, backup_root, passphrase, timestamp)
        build_manifest(
            backup_root,
            archive_path.name,
            digest,
            components,
            remote_results,
            args.include_heavy_feeds,
        )
        (backup_root / "LATEST_BACKUP.txt").write_text(archive_path.name + "\n", encoding="utf-8")

        # Local sha verify
        chk = _run(["sha256sum", "-c", f"{archive_path.name}.sha256"], cwd=backup_root)
        if chk.returncode != 0:
            raise RuntimeError("Local SHA-256 verification failed")

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
            # Verify remote listing contains archive
            import smbclient  # type: ignore

            host, share = _smb_connect()
            remote = set(smbclient.listdir(fr"\\{host}\{share}"))
            needed = {
                archive_path.name,
                f"{archive_path.name}.sha256",
                "infrastructure_manifest.json",
                "LATEST_BACKUP.txt",
            }
            missing = needed - remote
            if missing:
                raise RuntimeError(f"USB share missing after upload: {sorted(missing)}")
            _log(f"USB verify OK — {len(needed)} required files present on share")

        _log("SUCCESS — complete backup")
        _log(f"Encrypted archive: {archive_path}")
        for r in remote_results:
            if r.get("vm_id") != 100:
                _log(
                    f"  VM{r.get('vm_id')} {r.get('ip')}: {r.get('status')} "
                    f"bytes={r.get('bytes')} vols={len(r.get('volumes') or [])} "
                    f"skipped_heavy={len(r.get('skipped_heavy') or [])}"
                )
        return 0
    finally:
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
