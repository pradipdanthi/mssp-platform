#!/usr/bin/env python3
"""Junexis catalogue engine worker — long-running idle-capable process per svc-XX.

Installed on the appliance ISO. systemd units stay disabled until license reconcile
enables them. Each worker verifies its backend toolchain is on disk and then runs
a readiness/heartbeat loop (and service-specific work hooks).
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
from pathlib import Path

STATE = Path(os.environ.get("JUNEXIS_STATE_DIR", "/var/lib/junexis"))
LOG_DIR = Path(os.environ.get("JUNEXIS_LOG_DIR", "/var/log/junexis"))
ENGINE_BIN = Path(os.environ.get("JUNEXIS_ENGINE_BIN", "/opt/junexis/engines/bin"))

# Backend tools that must exist on disk for each catalogue service
REQUIRED = {
    "svc-01": ["wazuh-manager", "fluent-bit"],
    "svc-02": ["junexis-engine-api"],  # IR jobs via local appliance API
    "svc-03": ["junexis-engine-api"],  # containment jobs via local API
    "svc-04": ["nuclei", "vuls"],  # VMaaS scanners
    "svc-05": ["wazuh-manager"],  # SCA rides on local Manager
    "svc-06": ["suricata", "zeek"],  # NDR
    "svc-07": ["junexis-engine-api"],  # IOC/hunt via DuckDB lake
    "svc-08": ["junexis-engine-api"],  # forensics/archiver hooks
    "svc-09": ["nuclei"],  # EASM probes reuse nuclei templates/targets
    "svc-10": ["junexis-engine-api"],  # IdP connectors (channel + local API)
}

STOP = False


def _which(name: str) -> str | None:
    if name in ("wazuh-manager", "fluent-bit", "suricata", "zeek"):
        # package binaries / services
        candidates = {
            "wazuh-manager": ["/var/ossec/bin/wazuh-control", "/usr/bin/wazuh-control"],
            "fluent-bit": ["/opt/fluent-bit/bin/fluent-bit", "/usr/bin/fluent-bit"],
            "suricata": ["/usr/bin/suricata"],
            "zeek": ["/opt/zeek/bin/zeek", "/usr/bin/zeek", "/opt/zeek-lts/bin/zeek"],
        }
        for p in candidates.get(name, []):
            if Path(p).exists():
                return p
        # zeekctl path
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
    """Best-effort start of package daemons when this catalogue unit is enabled."""
    if svc == "svc-01":
        subprocess.run(["systemctl", "start", "wazuh-manager"], check=False)
        subprocess.run(["systemctl", "start", "fluent-bit"], check=False)
    elif svc == "svc-05":
        subprocess.run(["systemctl", "start", "wazuh-manager"], check=False)
    elif svc == "svc-06":
        subprocess.run(["systemctl", "start", "suricata"], check=False)
        # zeek often via zeekctl
        for ctl in ("/opt/zeek/bin/zeekctl", "/opt/zeek-lts/bin/zeekctl"):
            if Path(ctl).exists():
                subprocess.run([ctl, "deploy"], check=False)
                break
    elif svc == "svc-04":
        # scanners are on-demand; ensure templates dir exists
        Path("/var/lib/junexis/vmaas").mkdir(parents=True, exist_ok=True)


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
        heartbeat = {
            "svc": svc,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "running",
            "backends": report["found"],
        }
        (STATE / "engine-status" / f"{svc}.json").write_text(
            json.dumps(heartbeat, indent=2) + "\n", encoding="utf-8"
        )
        time.sleep(interval)
    log.info("stopping %s", svc)
    stop_backend(svc)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Junexis catalogue engine worker")
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
