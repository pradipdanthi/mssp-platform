#!/usr/bin/env python3
"""Kevantic catalogue engine worker — long-running idle-capable process per svc-XX.

Installed on the appliance ISO. systemd units stay disabled until license reconcile
enables them. Each worker verifies its backend toolchain is on disk, then runs a
readiness/heartbeat loop and claims jobs from kevantic-engine-api.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

STATE = Path(os.environ.get("KEVANTIC_STATE_DIR", "/var/lib/kevantic"))
LOG_DIR = Path(os.environ.get("KEVANTIC_LOG_DIR", "/var/log/kevantic"))
ENGINE_BIN = Path(os.environ.get("KEVANTIC_ENGINE_BIN", "/opt/kevantic/engines/bin"))
ENGINE_API = os.environ.get("KEVANTIC_ENGINE_API", "http://127.0.0.1:8787")

# Backend tools that must exist on disk for each catalogue service
REQUIRED = {
    "svc-01": ["wazuh-manager", "fluent-bit"],
    "svc-02": ["kevantic-engine-api"],
    "svc-03": ["kevantic-engine-api"],
    "svc-04": ["nuclei", "vuls"],
    "svc-05": ["wazuh-manager"],
    "svc-06": ["suricata", "zeek"],
    "svc-07": ["kevantic-engine-api"],
    "svc-08": ["kevantic-engine-api"],
    "svc-09": ["nuclei", "kevantic-engine-api"],
    "svc-10": ["kevantic-engine-api"],
}

JOB_SERVICES = frozenset({"svc-02", "svc-03", "svc-07", "svc-08", "svc-09", "svc-10"})

STOP = False


def _which(name: str) -> str | None:
    if name == "kevantic-engine-api":
        for p in ("/usr/bin/kevantic-engine-api", "/usr/local/bin/kevantic-engine-api"):
            if Path(p).exists():
                return p
        # API process ready marker or live health
        if (STATE / "engine-api.ready").exists():
            return str(STATE / "engine-api.ready")
        try:
            with urllib.request.urlopen(f"{ENGINE_API}/appliance/v1/health", timeout=2) as resp:
                if resp.status == 200:
                    return ENGINE_API
        except Exception:
            pass
        return shutil.which(name)
    if name in ("wazuh-manager", "fluent-bit", "suricata", "zeek"):
        candidates = {
            "wazuh-manager": ["/var/ossec/bin/wazuh-control", "/usr/bin/wazuh-control"],
            "fluent-bit": ["/opt/fluent-bit/bin/fluent-bit", "/usr/bin/fluent-bit"],
            "suricata": ["/usr/bin/suricata"],
            "zeek": ["/opt/zeek/bin/zeek", "/usr/bin/zeek", "/opt/zeek-lts/bin/zeek"],
        }
        for p in candidates.get(name, []):
            if Path(p).exists():
                return p
        if name == "zeek":
            for p in ("/opt/zeek/bin/zeekctl", "/opt/zeek-lts/bin/zeekctl"):
                if Path(p).exists():
                    return p
        return shutil.which(name)
    if name in ("nuclei", "vuls", "vuls-scanner"):
        p = ENGINE_BIN / name
        if p.exists():
            return str(p)
        return shutil.which(name)
    return shutil.which(name)


def verify_tools(svc: str) -> dict:
    missing = []
    found = {}
    for tool in REQUIRED.get(svc, []):
        path = _which(tool)
        if path:
            found[tool] = path
        else:
            missing.append(tool)
    return {"svc": svc, "found": found, "missing": missing, "ok": not missing}


def ensure_backend_running(svc: str) -> None:
    if svc == "svc-01":
        subprocess.run(["systemctl", "start", "wazuh-manager"], check=False)
        subprocess.run(["systemctl", "start", "fluent-bit"], check=False)
    elif svc == "svc-05":
        subprocess.run(["systemctl", "start", "wazuh-manager"], check=False)
    elif svc == "svc-06":
        subprocess.run(["systemctl", "start", "suricata"], check=False)
        for ctl in ("/opt/zeek/bin/zeekctl", "/opt/zeek-lts/bin/zeekctl"):
            if Path(ctl).exists():
                subprocess.run([ctl, "deploy"], check=False)
                break
    elif svc == "svc-04":
        Path("/var/lib/kevantic/vmaas").mkdir(parents=True, exist_ok=True)
    elif svc in JOB_SERVICES:
        subprocess.run(["systemctl", "start", "kevantic-appliance-engine"], check=False)


def stop_backend(svc: str) -> None:
    if svc == "svc-01":
        subprocess.run(["systemctl", "stop", "wazuh-manager"], check=False)
        subprocess.run(["systemctl", "stop", "fluent-bit"], check=False)
    elif svc == "svc-06":
        subprocess.run(["systemctl", "stop", "suricata"], check=False)
        for ctl in ("/opt/zeek/bin/zeekctl", "/opt/zeek-lts/bin/zeekctl"):
            if Path(ctl).exists():
                subprocess.run([ctl, "stop"], check=False)
                break


def _http_json(url: str, *, method: str = "GET", body: dict | None = None, timeout: float = 10.0) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def process_one_job(svc: str, log: logging.Logger) -> bool:
    """Claim and execute one local job. Returns True if a job was processed."""
    try:
        claim = _http_json(
            f"{ENGINE_API}/appliance/v1/jobs/claim?svc={svc}&worker_id={svc}-worker"
        )
    except Exception as exc:
        log.debug("claim failed: %s", exc)
        return False
    job = claim.get("job") if isinstance(claim, dict) else None
    if not job:
        return False
    job_id = job.get("job_id")
    log.info("claimed job %s type=%s", job_id, job.get("job_type"))
    try:
        # Prefer execute endpoint so executor stays in engine-api process
        result = _http_json(
            f"{ENGINE_API}/appliance/v1/jobs/{job_id}/execute",
            method="POST",
            body={},
            timeout=180.0,
        )
        log.info("job %s done success=%s", job_id, result.get("success"))
    except Exception as exc:
        log.warning("job %s execute failed: %s", job_id, exc)
        try:
            _http_json(
                f"{ENGINE_API}/appliance/v1/jobs/{job_id}/complete",
                method="POST",
                body={"success": False, "result": {"error": str(exc)[:300]}},
            )
        except Exception:
            pass
    return True


def _handle_signal(signum, frame) -> None:  # noqa: ARG001
    global STOP
    STOP = True


def run_worker(svc: str, interval: int) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / f"engine-{svc}.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    log = logging.getLogger(svc)
    # Wait briefly for engine-api on job services
    if svc in JOB_SERVICES:
        for _ in range(15):
            if _which("kevantic-engine-api"):
                break
            time.sleep(2)
    report = verify_tools(svc)
    (STATE / "engine-status").mkdir(parents=True, exist_ok=True)
    (STATE / "engine-status" / f"{svc}.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    if report["missing"]:
        log.error("missing backend tools: %s", report["missing"])
        return 2
    log.info("backends ready: %s", report["found"])
    ensure_backend_running(svc)
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    while not STOP:
        jobs_done = 0
        if svc in JOB_SERVICES:
            # Drain a few jobs per tick
            for _ in range(5):
                if not process_one_job(svc, log):
                    break
                jobs_done += 1
        heartbeat = {
            "svc": svc,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "running",
            "backends": report["found"],
            "jobs_processed_tick": jobs_done,
        }
        (STATE / "engine-status" / f"{svc}.json").write_text(
            json.dumps(heartbeat, indent=2) + "\n", encoding="utf-8"
        )
        time.sleep(interval)
    log.info("stopping %s", svc)
    stop_backend(svc)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Kevantic catalogue engine worker")
    ap.add_argument("svc", help="svc-01 .. svc-10")
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()
    if args.svc not in REQUIRED:
        print(f"unknown svc: {args.svc}", file=sys.stderr)
        return 2
    if args.verify_only:
        print(json.dumps(verify_tools(args.svc), indent=2))
        return 0 if verify_tools(args.svc)["ok"] else 2
    return run_worker(args.svc, args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
