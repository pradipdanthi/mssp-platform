#!/usr/bin/env python3
"""NikTiar Secure Edge agent — heartbeat + ship WAF/block signals to control plane."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests
import yaml

CFG = yaml.safe_load(Path("/app/config.yaml").read_text()) if Path("/app/config.yaml").exists() else {}
CONTROL = (os.getenv("NIKTIAR_CONTROL_URL") or "").rstrip("/")
TOKEN = os.getenv("NIKTIAR_APPLIANCE_TOKEN") or ""
TENANT = os.getenv("NIKTIAR_TENANT_CODE") or ""
HOST = os.getenv("SECURE_EDGE_HOSTNAME") or "niktiar-secure-edge"
POLL = int(CFG.get("poll_seconds") or 30)


def headers():
    h = {"Content-Type": "application/json", "User-Agent": "NikTiar-SecureEdge/0.1"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def heartbeat():
    if not CONTROL:
        print("heartbeat skip: NIKTIAR_CONTROL_URL unset", flush=True)
        return
    url = CONTROL + (CFG.get("heartbeat_path") or "/api/v1/secure-edge/heartbeat")
    body = {
        "hostname": HOST,
        "tenant_short_code": TENANT or None,
        "status": "online",
        "version": "0.1.0",
        "capabilities": ["waf_modsecurity_crs", "crowdsec", "nginx"],
    }
    try:
        r = requests.post(url, headers=headers(), json=body, timeout=15)
        print(f"heartbeat {r.status_code}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"heartbeat error: {exc}", flush=True)


def main():
    print(f"NikTiar Secure Edge agent starting host={HOST} control={CONTROL or 'NONE'}", flush=True)
    while True:
        heartbeat()
        time.sleep(POLL)


if __name__ == "__main__":
    main()
