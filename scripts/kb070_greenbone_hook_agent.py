#!/usr/bin/env python3
"""KB-070: Instant Greenbone scan-done hook agent (runs on VM 109).

Greenbone Alert (HTTP Get) hits this agent when a task reaches Done.
The agent pulls GMP results via python-gvm (password from file, not argv)
and POSTs them to MSSP Control Plane /integrations/vuln/sync.

Secrets are host-local only (never Git).
"""

from __future__ import annotations

import hmac
import json
import os
import re
import subprocess
import sys
import threading
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

LISTEN_HOST = os.environ.get("MSSP_HOOK_LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("MSSP_HOOK_LISTEN_PORT", "9271"))
CONTROL_PLANE_URL = os.environ.get(
    "CONTROL_PLANE_URL", "http://192.168.0.201:8000"
).rstrip("/")
COMPOSE_FILE = os.environ.get(
    "GREENBONE_COMPOSE_FILE", "/opt/mssp-greenbone/community/compose.yaml"
)
COMPOSE_PROJECT = os.environ.get(
    "GREENBONE_COMPOSE_PROJECT", "greenbone-community-edition"
)
SECRET_DIR = Path(
    os.environ.get("MSSP_GREENBONE_SECRET_DIR", "/opt/mssp-greenbone/secrets")
)
HOOK_TOKEN_FILE = SECRET_DIR / "hook_token"
VULN_SYNC_KEY_FILE = SECRET_DIR / "vuln_sync_api_key"
ADMIN_PASSWORD_FILE = SECRET_DIR / "admin.password"
ADMIN_USER_FILE = SECRET_DIR / "admin.user"
MAP_FILE = Path(
    os.environ.get(
        "GREENBONE_HOST_MAP_FILE",
        "/opt/mssp-greenbone/config/greenbone_host_tenant_map.yml",
    )
)
MIN_QOD = os.environ.get("GREENBONE_MIN_QOD", "70")
LEVELS = os.environ.get("GREENBONE_LEVELS", "hml")
ROWS = os.environ.get("GREENBONE_RESULT_ROWS", "500")

_pull_lock = threading.Lock()

_GMP_PY = r"""
import sys
from pathlib import Path
from gvm.connections import UnixSocketConnection
from gvm.protocols.gmp import Gmp
from gvm.transforms import EtreeCheckCommandTransform
from lxml import etree

user = Path("/run/mssp/admin.user").read_text(encoding="utf-8").strip() or "admin"
password = Path("/run/mssp/admin.password").read_text(encoding="utf-8").strip()
filter_term = Path("/run/mssp/filter.txt").read_text(encoding="utf-8").strip()
conn = UnixSocketConnection(path="/run/gvmd/gvmd.sock", timeout=120)
transform = EtreeCheckCommandTransform()
with Gmp(connection=conn, transform=transform) as gmp:
    gmp.authenticate(user, password)
    response = gmp.get_results(filter_string=filter_term, details=True)
    sys.stdout.write(etree.tostring(response, encoding="unicode"))
"""


def read_secret(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def load_map(text: str) -> dict:
    default = ""
    hosts: dict = {}
    mode = None
    current = None
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith("default_tenant_short_code:"):
            default = line.split(":", 1)[1].strip().strip("'\"")
            continue
        if line.startswith("hosts:"):
            mode = "hosts"
            continue
        if mode == "hosts":
            match = (
                re.match(r'^  "([^"]+)":\s*$', line)
                or re.match(r"^  '([^']+)':\s*$", line)
                or re.match(r"^  ([^:#]+):\s*$", line)
            )
            if match:
                current = match.group(1).strip()
                hosts[current] = {}
                continue
            if current and re.match(r"^    ", line):
                key, _, val = line.strip().partition(":")
                hosts[current][key.strip()] = val.strip().strip("'\"")
    return {"default_tenant_short_code": default, "hosts": hosts}


def gmp_get_results(filter_term: str) -> str:
    """Fetch GMP results via python-gvm inside gvm-tools.

    Password is passed as a mounted file, never on sudo/docker argv.
    """
    if not ADMIN_PASSWORD_FILE.exists():
        raise RuntimeError("admin.password missing in secrets dir")
    runtime = SECRET_DIR / ".runtime"
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    filter_path = runtime / "filter.txt"
    script_path = runtime / "gmp_query.py"
    pass_mount = runtime / "admin.password"
    user_mount = runtime / "admin.user"
    filter_path.write_text(filter_term, encoding="utf-8")
    script_path.write_text(_GMP_PY, encoding="utf-8")
    user = read_secret(ADMIN_USER_FILE) or "admin"
    user_mount.write_text(user + "\n", encoding="utf-8")
    pass_mount.write_text(read_secret(ADMIN_PASSWORD_FILE) + "\n", encoding="utf-8")
    # gvm-tools runs as uid 1001 — mounts must be world-readable briefly
    for path in (filter_path, script_path, pass_mount, user_mount):
        path.chmod(0o644)

    cmd = [
        "sudo",
        "docker",
        "compose",
        "-f",
        COMPOSE_FILE,
        "-p",
        COMPOSE_PROJECT,
        "run",
        "--rm",
        "--no-deps",
        "--user",
        "1001",
        "-v",
        f"{pass_mount}:/run/mssp/admin.password:ro",
        "-v",
        f"{user_mount}:/run/mssp/admin.user:ro",
        "-v",
        f"{filter_path}:/run/mssp/filter.txt:ro",
        "-v",
        f"{script_path}:/run/mssp/gmp_query.py:ro",
        "--entrypoint",
        "python3",
        "gvm-tools",
        "/run/mssp/gmp_query.py",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    for path in (filter_path, script_path, pass_mount, user_mount):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"gmp query failed rc={proc.returncode}")
    out = proc.stdout.strip()
    idx = out.find("<")
    if idx < 0:
        raise RuntimeError("gmp query returned no XML")
    return out[idx:]


def severity_of(result: ET.Element) -> str:
    threat = (result.findtext("threat") or "").strip().lower()
    try:
        score = float((result.findtext("severity") or "0").strip() or 0)
    except ValueError:
        score = 0.0
    if score >= 9.0 or threat == "critical":
        return "critical"
    if score >= 7.0 or threat == "high":
        return "high"
    if score >= 4.0 or threat == "medium":
        return "medium"
    if threat in ("log", "false positive"):
        return ""
    if threat == "low" or score > 0:
        return "low"
    return ""


def first_cve(nvt: ET.Element | None) -> str | None:
    if nvt is None:
        return None
    direct = (nvt.findtext("cve") or "").strip()
    if direct and direct.upper() != "NOCVE":
        return direct.split(",")[0].strip()[:64]
    refs = nvt.find("refs")
    if refs is not None:
        for ref in refs.findall("ref"):
            if (ref.get("type") or "").lower() == "cve" and ref.get("id"):
                return ref.get("id").strip()[:64]
    return None


def host_key(result: ET.Element) -> str:
    host_el = result.find("host")
    if host_el is None:
        return ""
    text = "".join(host_el.itertext()).strip()
    match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", text)
    if match:
        return match.group(1)
    return text.split()[0] if text else ""


def parse_results(xml_text: str, mapping: dict) -> dict[str, list]:
    root = ET.fromstring(xml_text)
    default_tenant = mapping["default_tenant_short_code"].upper()
    host_map = mapping.get("hosts") or {}
    batches: dict[str, list] = {}
    for result in root.findall("result"):
        rid = result.get("id") or ""
        if not rid:
            continue
        sev = severity_of(result)
        if not sev:
            continue
        nvt = result.find("nvt")
        title = (
            result.findtext("name")
            or (nvt.findtext("name") if nvt is not None else None)
            or "Greenbone finding"
        ).strip()[:500]
        host = host_key(result)
        meta = host_map.get(host) or {}
        tenant = (meta.get("tenant_short_code") or default_tenant or "").strip().upper()
        if not tenant:
            # Fail-closed: never attach findings to a demo/default tenant.
            continue
        asset_hostname = meta.get("asset_hostname") or None
        desc = (result.findtext("description") or "").strip()
        summary = desc[:1200] if desc else f"Vulnerability finding on {host or 'unknown host'}."
        remediation = None
        sol = nvt.find("solution") if nvt is not None else None
        if sol is not None and (sol.text or "").strip():
            remediation = sol.text.strip()[:4000]
        elif desc:
            remediation = (
                "Review the finding and apply vendor updates where applicable.\n\n"
                + desc[:1500]
            )[:4000]
        finding = {
            "external_finding_id": rid,
            "title": title,
            "severity": sev,
            "cve_id": first_cve(nvt),
            "nvt_oid": (nvt.get("oid") if nvt is not None else None),
            "asset_hostname": asset_hostname,
            "customer_safe_summary": summary[:5000],
            "remediation_summary": remediation,
            "create_recommendation": None,
            "recommendation_customer_visible": False,
        }
        batches.setdefault(tenant, []).append(finding)
    return batches


def pull_and_sync() -> dict:
    mapping = load_map(MAP_FILE.read_text(encoding="utf-8"))
    filter_term = (
        f"apply_overrides=0 levels={LEVELS} min_qod={MIN_QOD} "
        f"rows={ROWS} first=1 sort-reverse=severity"
    )
    xml_text = gmp_get_results(filter_term)
    batches = parse_results(xml_text, mapping)
    sync_key = read_secret(VULN_SYNC_KEY_FILE)
    if not sync_key:
        raise RuntimeError("vuln sync key missing on greenbone host")
    synced = 0
    for tenant, findings in sorted(batches.items()):
        for i in range(0, len(findings), 100):
            chunk = findings[i : i + 100]
            body = {
                "tenant_short_code": tenant,
                "source_platform": "greenbone",
                "findings": chunk,
            }
            req = urllib.request.Request(
                CONTROL_PLANE_URL + "/integrations/vuln/sync",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Vuln-Sync-Key": sync_key,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            synced += len(data.get("results") or [])
    return {"synced": synced, "tenants": len(batches)}


class HookHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("hook: " + (fmt % args) + "\n")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        token = None
        if len(parts) == 2 and parts[0] == "hook":
            token = parts[1]
        elif len(parts) == 3 and parts[0] == "mssp" and parts[1] == "pull":
            token = parts[2]
        if token is not None:
            expected = read_secret(HOOK_TOKEN_FILE)
            if not expected or not hmac.compare_digest(token.strip(), expected.strip()):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"not found")
                return
            threading.Thread(target=run_pull_safe, daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"pull-started")
            return
        if parsed.path in ("/health", "/"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(404)
        self.end_headers()


def run_pull_safe() -> None:
    if not _pull_lock.acquire(blocking=False):
        sys.stderr.write("hook: pull already running\n")
        return
    try:
        result = pull_and_sync()
        sys.stderr.write(f"hook: pull done synced={result.get('synced')}\n")
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"hook: pull failed: {exc}\n")
    finally:
        _pull_lock.release()


def main() -> None:
    SECRET_DIR.mkdir(parents=True, exist_ok=True)
    if not HOOK_TOKEN_FILE.exists() or not VULN_SYNC_KEY_FILE.exists():
        raise SystemExit(
            f"Missing secrets in {SECRET_DIR} (need hook_token and vuln_sync_api_key)"
        )
    if not ADMIN_PASSWORD_FILE.exists():
        raise SystemExit(f"Missing {ADMIN_PASSWORD_FILE}")
    if not MAP_FILE.exists():
        raise SystemExit(f"Missing host map: {MAP_FILE}")
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), HookHandler)
    sys.stderr.write(
        f"mssp greenbone hook listening on {LISTEN_HOST}:{LISTEN_PORT} "
        f"-> {CONTROL_PLANE_URL}\n"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
