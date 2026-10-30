#!/usr/bin/env python3
"""READ-ONLY baseline of the CURRENTLY DEPLOYED chat path (production VM 100 -> VM 117 Cursor CLI).

Sends only read-only questions (no write keywords, apply_actions=false), as the validation SOC analyst
from .secrets/validation.env (never printed). Side effect: the live console activity feed shows
"Tia query" entries, exactly as when an operator asks. Records timings and outcome categories only;
answer text is not stored (it can contain customer data).

While it runs, it samples (read-only, over the existing SSH access): VM 117 vmstat and number of
running cursor-agent processes, and the Proxmox node's vmstat plus per-VM CPU for VMs 100 and 117.

    python3 scripts/tia_prod_chat_baseline.py --out docs/tia_measurements/<dir>
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
QUESTIONS = [
    ("status_count", "How many critical alerts do we have?", 8),
    ("case_evidence", "Tell me about the most recent critical alert and what evidence it has.", 6),
    ("engine_status", "Are the security engines healthy right now?", 4),
]


def creds():
    kv = {}
    for line in open("/opt/mssp-control/.secrets/validation.env"):
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            kv[k] = v
    return kv["SOC_ANALYST_EMAIL"], kv["SOC_ANALYST_PASSWORD"]


def post(path, body, token=None, timeout=60):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    t0 = time.time()
    m0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}"), t0, time.monotonic() - m0
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read() or b"{}")
        except Exception:  # noqa: BLE001
            detail = {}
        return e.code, detail, t0, time.monotonic() - m0
    except Exception as e:  # noqa: BLE001
        return 0, {"error": type(e).__name__}, t0, time.monotonic() - m0


def sampler(cmd, path):
    return subprocess.Popen(cmd, stdout=open(path, "w"), stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    email, pw = creds()
    st, body, _, _ = post("/auth/login", {"email": email, "password": pw, "portal": "admin"})
    token = body.get("access_token")
    if st != 200 or not token:
        raise SystemExit(f"login failed HTTP {st}")
    agent_ssh = ["ssh", "-o", "BatchMode=yes", "-i", os.path.expanduser("~/.ssh/id_ed25519_soc_agent"), "192.168.0.228"]
    procs = [
        sampler(agent_ssh + ["while true; do echo \"$(date +%s.%N) $(pgrep -c -f cursor-agent) $(cat /proc/loadavg | cut -d' ' -f1)\"; sleep 0.5; done"], f"{a.out}/vm117_cli_procs.txt"),
        sampler(agent_ssh + ["vmstat -t 1"], f"{a.out}/vm117_vmstat.txt"),
        sampler(["ssh", "-o", "BatchMode=yes", "proxmox", "vmstat -t 1"], f"{a.out}/proxmox_vmstat.txt"),
        sampler(["ssh", "-o", "BatchMode=yes", "proxmox",
                 "while true; do for v in 100 117; do echo \"$(date +%s) $v $(pvesh get /nodes/$(hostname)/qemu/$v/status/current --output-format json | python3 -c 'import json,sys;d=json.load(sys.stdin);print(round(d.get(\"cpu\",0)*100,1), d.get(\"cpus\"), round(d.get(\"mem\",0)/2**20), round(d.get(\"maxmem\",0)/2**20))')\"; done; sleep 2; done"],
                f"{a.out}/proxmox_vm_cpu.txt"),
    ]
    rows = []
    try:
        time.sleep(3)
        for label, q, n in QUESTIONS:
            for i in range(n):
                st, body, t0, dt = post("/admin/soc-console/chat", {"message": q, "apply_actions": False}, token)
                rows.append({"label": label, "mode": "serial", "i": i, "start_epoch": round(t0, 3), "seconds": round(dt, 3), "http": st,
                             "provider": (body or {}).get("provider"), "answer_chars": len((body or {}).get("answer") or ""),
                             "error": str((body or {}).get("detail") or (body or {}).get("error") or "")[:80]})
                print(rows[-1], flush=True)
                time.sleep(1)
        for rnd in range(2):
            with cf.ThreadPoolExecutor(3) as pool:
                futs = [pool.submit(post, "/admin/soc-console/chat", {"message": QUESTIONS[0][1], "apply_actions": False}, token) for _ in range(3)]
                for i, f in enumerate(futs):
                    st, body, t0, dt = f.result()
                    rows.append({"label": "status_count", "mode": "concurrent3", "i": rnd * 3 + i, "start_epoch": round(t0, 3), "seconds": round(dt, 3), "http": st,
                                 "provider": (body or {}).get("provider"), "answer_chars": len((body or {}).get("answer") or ""),
                                 "error": str((body or {}).get("detail") or (body or {}).get("error") or "")[:80]})
                    print(rows[-1], flush=True)
        time.sleep(3)
    finally:
        for p in procs:
            p.terminate()
    with open(f"{a.out}/prod_chat_baseline.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
