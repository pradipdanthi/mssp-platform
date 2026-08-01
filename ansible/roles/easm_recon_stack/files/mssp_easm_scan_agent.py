#!/usr/bin/env python3
"""
MSSP EASM deep recon agent (VM 109).
Pulls GET /integrations/easm/scan-plan → Amass (+ optional Nuclei) → POST /integrations/easm/sync.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Set
from urllib import error, request

CONTROL_PLANE_URL = os.environ.get("CONTROL_PLANE_URL", "http://192.168.0.201:8000").rstrip("/")
KEY_FILE = os.environ.get(
    "EASM_SYNC_API_KEY_FILE", "/opt/mssp-easm-agent/secrets/easm_sync_api_key"
)
AMASS_BIN = os.environ.get("AMASS_BIN", "/opt/mssp-easm-agent/bin/amass")
NUCLEI_BIN = os.environ.get("NUCLEI_BIN", "/opt/mssp-vuln-free/bin/nuclei")
NUCLEI_TEMPLATES = os.environ.get(
    "NUCLEI_TEMPLATES", "/opt/mssp-vuln-free/nuclei-templates"
)
WORK = Path(os.environ.get("EASM_WORK", "/opt/mssp-easm-agent/work"))
WORK.mkdir(parents=True, exist_ok=True)

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
)


def _key() -> str:
    return Path(KEY_FILE).read_text(encoding="utf-8").strip()


def _api(method: str, path: str, body: dict | None = None) -> Any:
    data = None
    headers = {"X-Easm-Sync-Key": _key()}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(
        CONTROL_PLANE_URL + path, data=data, headers=headers, method=method
    )
    with request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _amass_enum(domain: str) -> Set[str]:
    out: Set[str] = {domain.lower()}
    if not Path(AMASS_BIN).exists():
        print(f"amass missing at {AMASS_BIN}", file=sys.stderr)
        return out
    # Passive-first to reduce noise; timeout capped.
    cmd = [
        AMASS_BIN,
        "enum",
        "-passive",
        "-d",
        domain,
        "-nocolor",
        "-silent",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"amass failed: {exc}", file=sys.stderr)
        return out
    for line in (proc.stdout or "").splitlines():
        host = line.strip().lower().rstrip(".")
        if host and DOMAIN_RE.match(host):
            out.add(host)
    return out


def _nuclei_http(hosts: List[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    if not Path(NUCLEI_BIN).exists() or not hosts:
        return findings
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as fh:
        for h in hosts[:50]:
            fh.write(f"https://{h}\n")
            fh.write(f"http://{h}\n")
        targets = fh.name
    out_jsonl = WORK / "nuclei-easm.jsonl"
    cmd = [
        NUCLEI_BIN,
        "-l",
        targets,
        "-t",
        NUCLEI_TEMPLATES,
        "-severity",
        "critical,high,medium",
        "-jsonl",
        "-o",
        str(out_jsonl),
        "-silent",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except Exception as exc:  # noqa: BLE001
        print(f"nuclei failed: {exc}", file=sys.stderr)
        return findings
    if not out_jsonl.exists():
        return findings
    for line in out_jsonl.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        info = obj.get("info") or {}
        host = str(obj.get("host") or obj.get("matched-at") or "")
        findings.append(
            {
                "asset_name": host[:255],
                "finding_type": "WEB_VULNERABILITY",
                "severity": str(info.get("severity") or "medium").upper(),
                "title": str(info.get("name") or obj.get("template-id") or "Exposure")[:500],
                "description": str(info.get("description") or "")[:4000]
                or "External exposure detected by perimeter templates.",
                "remediation": "Review exposure with SOC and harden or remove public service.",
            }
        )
    return findings


def main() -> int:
    if not Path(KEY_FILE).exists():
        print(f"missing key file {KEY_FILE}", file=sys.stderr)
        return 1
    try:
        plan = _api("GET", "/integrations/easm/scan-plan")
    except error.HTTPError as exc:
        print(f"scan-plan HTTP {exc.code}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"scan-plan failed: {exc}", file=sys.stderr)
        return 1

    tenants = plan.get("tenants") or []
    if not tenants:
        print("no easm tenants due")
        return 0

    for tenant in tenants:
        short = tenant.get("short_code")
        tid = tenant.get("tenant_id")
        targets = tenant.get("targets") or []
        for target in targets:
            domain = str(target.get("domain") or "").strip().lower().rstrip(".")
            if not domain:
                continue
            hosts = sorted(_amass_enum(domain))
            assets = []
            for h in hosts:
                atype = "PRIMARY_DOMAIN" if h == domain else "SUBDOMAIN"
                assets.append(
                    {
                        "domain_or_ip": h,
                        "asset_type": atype,
                        "discovery_source": "amass_passive",
                    }
                )
            findings = _nuclei_http(hosts[:30])
            payload = {
                "tenant_short_code": short,
                "tenant_id": tid,
                "target_domain": domain,
                "engine": "AMASS_NUCLEI",
                "assets": assets,
                "findings": findings,
            }
            try:
                result = _api("POST", "/integrations/easm/sync", payload)
                print(f"synced {short} {domain}: {result}")
            except Exception as exc:  # noqa: BLE001
                print(f"sync failed {short} {domain}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
