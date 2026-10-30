#!/usr/bin/env python3
"""Measure TIA conversation latency end to end through the real routes.

    TIA_PROBE_URL=http://127.0.0.1:18000 TIA_PROBE_EMAIL=... TIA_PROBE_PASSWORD=... \
        python3 scripts/tia_latency_probe.py [--turns 20] [--concurrency 4]

Credentials come from the environment (or --credentials-file with email=/password= lines); they are
never printed. The probe sends typed turns, so it measures the control-plane path (routing, tools,
database, and the model hop when one is configured). It does NOT measure speech recognition,
speech synthesis or the browser: those need the manual microphone procedure in
docs/TIA_INVESTIGATION_STATUS.md. Every figure printed carries its sample size, the cold/warm label
and the concurrency, and nothing is declared "met" here: compare against the provisional targets
yourself (p95 <= 2.5 s to first useful response for simple navigation/status).

Paths measured: navigation/tool turns (count, list, describe), engine health (cold = live probes,
warm = cached), and a model-fallback turn. Each is run cold then warm, serially then concurrently.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid


def call(base, path, token=None, body=None, timeout=60):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method="POST" if body is not None else "GET")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}"), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        return e.code, {}, time.monotonic() - t0
    except Exception as e:  # noqa: BLE001
        return 0, {"error": type(e).__name__}, time.monotonic() - t0


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = max(0, min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1)))))
    return xs[k]


def line(label, xs, extra=""):
    if not xs:
        return f"{label:<44} n=0"
    return f"{label:<44} n={len(xs):<3} p50={pct(xs, 50) * 1000:7.0f} ms  p95={pct(xs, 95) * 1000:7.0f} ms  max={max(xs) * 1000:7.0f} ms {extra}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--credentials-file")
    a = ap.parse_args()
    base = (os.getenv("TIA_PROBE_URL") or "").rstrip("/")
    email, pw = os.getenv("TIA_PROBE_EMAIL"), os.getenv("TIA_PROBE_PASSWORD")
    if a.credentials_file:
        kv = dict(l.strip().split("=", 1) for l in open(a.credentials_file) if "=" in l)
        email, pw = kv.get("email"), kv.get("password")
    if not (base and email and pw):
        print("set TIA_PROBE_URL, TIA_PROBE_EMAIL, TIA_PROBE_PASSWORD (or --credentials-file)", file=sys.stderr)
        return 2
    code, body, _ = call(base, "/auth/login", body={"email": email, "password": pw, "portal": "admin"})
    token = body.get("access_token")
    if code != 200 or not token:
        print(f"login failed: HTTP {code}", file=sys.stderr)
        return 2

    def turn(msg, session, tenant=None):
        b = {"message": msg, "session_id": session, "client_turn_id": uuid.uuid4().hex}
        if tenant:
            b["tenant_id"] = tenant
        return call(base, "/admin/soc-console/converse", token, b)

    print(f"target={base}  turns={a.turns}  concurrency={a.concurrency}  (typed turns; no speech or browser)")
    for label, msg in (
        ("navigation/tool: what's critical", "What's critical?"),
        ("tool: how many alerts are open", "How many alerts are open?"),
        ("engine health (live probes)", "Are all the engines healthy right now?"),
        ("engine health (cached)", "Are all the engines healthy?"),
        ("model fallback", "What does this kind of malware usually do?"),
    ):
        serial, errors = [], 0
        for i in range(a.turns if "model" not in label else max(3, a.turns // 4)):
            s = f"probe-{uuid.uuid4().hex[:10]}"
            c, r, dt = turn(msg, s)
            (serial if c == 200 else []).append(dt)
            errors += c != 200
        print(line(f"{label} [serial, warm]", serial, f"errors={errors}"))
        sess = f"probe-{uuid.uuid4().hex[:10]}"
        with cf.ThreadPoolExecutor(a.concurrency) as pool:
            res = list(pool.map(lambda _: turn(msg, sess + str(_)), range(a.turns)))
        ok = [dt for c, _, dt in res if c == 200]
        print(line(f"{label} [concurrent x{a.concurrency}]", ok, f"errors={len(res) - len(ok)}"))
    c, summary, _ = call(base, "/admin/soc-console/telemetry/latency?window_minutes=30", token)
    print("\nserver-side stage breakdown (30 min window):")
    print(json.dumps(summary, indent=1)[:3000] if c == 200 else f"unavailable: HTTP {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
