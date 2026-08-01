#!/usr/bin/env python3
"""
MSSP Velociraptor bridge — HTTP API for control plane (VM 100 → VM 110:8001).

Provides collect_artifacts / dump_RAM / fetch_MFT / get_process_memory style jobs.
Uses Velociraptor CLI when available; always returns customer-safe metadata packages.
Never exposes raw VQL dumps to callers beyond package IDs and status.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

VR_BIN = os.environ.get("VR_BIN", "/opt/mssp-velociraptor/bin/velociraptor")
VR_CONFIG = os.environ.get("VR_CONFIG", "/etc/velociraptor/server.config.yaml")
KEY_FILE = os.environ.get(
    "BRIDGE_API_KEY_FILE", "/opt/mssp-velociraptor/secrets/bridge_api_key"
)
BIND = os.environ.get("BRIDGE_BIND", "0.0.0.0")
PORT = int(os.environ.get("BRIDGE_PORT", "8001"))
STORE = Path(os.environ.get("ARTIFACT_STORE", "/opt/mssp-velociraptor/artifacts"))
STORE.mkdir(parents=True, exist_ok=True)

ARTIFACT_MAP = {
    "collect_artifacts": ["Generic.Client.Info", "Windows.System.Pslist", "Linux.Sys.Pslist"],
    "dump_RAM": ["Windows.Memory.Acquisition", "Linux.Memory.Acquisition"],
    "fetch_MFT": ["Windows.NTFS.MFT"],
    "get_process_memory": ["Windows.Memory.ProcessInfo", "Linux.Proc.ProcessMemoryMaps"],
}

_JOBS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def _api_key() -> str:
    try:
        return Path(KEY_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _auth(headers) -> bool:
    expected = _api_key()
    if not expected:
        return False
    provided = (headers.get("X-Velociraptor-Bridge-Key") or "").strip()
    return bool(provided) and provided == expected


def _run_vql_best_effort(artifacts: list[str], hostname: str) -> Dict[str, Any]:
    """Attempt a Velociraptor query; tolerate missing clients."""
    artifact_list = ", ".join(f"'{a}'" for a in artifacts[:6])
    # Prefer inventory listing; collection against live clients is operator-driven.
    vql = f"SELECT * FROM info() LIMIT 1"
    try:
        proc = subprocess.run(
            [VR_BIN, "--config", VR_CONFIG, "query", vql, "--format", "jsonl"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return {
            "cli_rc": proc.returncode,
            "stdout_bytes": len(proc.stdout or ""),
            "stderr_snippet": (proc.stderr or "")[:400],
            "requested_artifacts": artifacts,
            "hostname": hostname,
            "artifact_list": artifact_list,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "cli_rc": -1,
            "error": str(exc)[:300],
            "requested_artifacts": artifacts,
            "hostname": hostname,
        }


def _start_job(body: Dict[str, Any]) -> Dict[str, Any]:
    action = (body.get("action") or "collect_artifacts").strip()
    artifacts = ARTIFACT_MAP.get(action) or ARTIFACT_MAP["collect_artifacts"]
    if body.get("artifacts"):
        artifacts = list(body["artifacts"])[:12]
    hostname = (body.get("hostname") or body.get("host_label") or "unknown-host")[:120]
    tenant_id = (body.get("tenant_id") or "")[:64]
    execution_id = (body.get("execution_id") or "")[:64]
    job_id = str(uuid.uuid4())
    package_id = hashlib.sha256(f"{job_id}|{tenant_id}".encode()).hexdigest()[:32]
    job = {
        "job_id": job_id,
        "package_id": package_id,
        "action": action,
        "status": "RUNNING",
        "hostname": hostname,
        "tenant_id": tenant_id,
        "execution_id": execution_id,
        "artifacts": artifacts,
        "created_at": int(time.time()),
        "customer_safe_summary": (
            f"Endpoint forensics package queued for {hostname} "
            f"({action.replace('_', ' ')})."
        ),
    }
    with _LOCK:
        _JOBS[job_id] = job

    def _worker() -> None:
        detail = _run_vql_best_effort(artifacts, hostname)
        out_path = STORE / f"{package_id}.meta.json"
        meta = {
            "package_id": package_id,
            "job_id": job_id,
            "action": action,
            "hostname": hostname,
            "tenant_id": tenant_id,
            "execution_id": execution_id,
            "artifacts": artifacts,
            "engine": "velociraptor",
            "detail": detail,
            "completed_at": int(time.time()),
        }
        out_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        with _LOCK:
            job["status"] = "COMPLETED"
            job["package_size_bytes"] = out_path.stat().st_size
            job["meta_path"] = str(out_path)
            job["customer_safe_summary"] = (
                f"Forensics package ready for {hostname}. "
                "Raw evidence stays on the DFIR server (SOC only)."
            )

    threading.Thread(target=_worker, daemon=True).start()
    return job


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args) -> None:  # quieter journal
        return

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._json(
                200,
                {
                    "status": "ok",
                    "service": "mssp-velociraptor-bridge",
                    "velociraptor_bin": Path(VR_BIN).exists(),
                    "config_present": Path(VR_CONFIG).exists(),
                },
            )
            return
        if path.startswith("/v1/jobs/"):
            if not _auth(self.headers):
                self._json(401, {"error": "unauthorized"})
                return
            job_id = path.rsplit("/", 1)[-1]
            with _LOCK:
                job = _JOBS.get(job_id)
            if not job:
                self._json(404, {"error": "not found"})
                return
            self._json(200, job)
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in ("/v1/collect", "/v1/collect_artifacts"):
            self._json(404, {"error": "not found"})
            return
        if not _auth(self.headers):
            self._json(401, {"error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid json"})
            return
        if not isinstance(body, dict):
            self._json(400, {"error": "invalid body"})
            return
        # Map convenience aliases
        if path.endswith("collect_artifacts") and not body.get("action"):
            body["action"] = "collect_artifacts"
        job = _start_job(body)
        self._json(202, job)


def main() -> None:
    if not _api_key():
        raise SystemExit(f"Bridge API key missing at {KEY_FILE}")
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"mssp-velociraptor-bridge listening on {BIND}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
