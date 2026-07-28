#!/usr/bin/env python3
"""
KB-079: Automated vulnerability scan agent (runs on VM 109 via systemd timer).
Pulls scan plan from control plane → Nuclei → POST findings. No manual steps.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

NUCLEI_BIN = os.environ.get("NUCLEI_BIN", "/opt/mssp-vuln-free/bin/nuclei")
NUCLEI_TEMPLATES = os.environ.get("NUCLEI_TEMPLATES", "/opt/mssp-vuln-free/nuclei-templates")
CONTROL_PLANE_URL = os.environ.get("CONTROL_PLANE_URL", "http://192.168.0.201:8000").rstrip("/")
KEY_FILE = os.environ.get(
    "VULN_SYNC_API_KEY_FILE", "/opt/mssp-vuln-free/secrets/vuln_sync_api_key"
)
SEVERITIES = os.environ.get("NUCLEI_SEVERITIES", "critical,high,medium")


def _key() -> str:
    return Path(KEY_FILE).read_text(encoding="utf-8").strip()


def _api(method: str, path: str, body: dict | None = None) -> Any:
    data = None
    headers = {"X-Vuln-Sync-Key": _key()}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        CONTROL_PLANE_URL + path, data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _severity(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in ("critical", "high", "medium", "low"):
        return s
    return "low"


def _normalize_jsonl(lines: str, tenant: str, targets: List[Dict[str, Any]]) -> List[dict]:
    host_to_asset: Dict[str, str | None] = {}
    for t in targets:
        target = str(t.get("target") or "")
        hint = t.get("asset_hostname")
        host_to_asset[target] = hint
        host_to_asset[target.split(":")[0]] = hint

    findings: List[dict] = []
    for line in lines.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        info = obj.get("info") or {}
        sev = _severity(str(info.get("severity") or "low"))
        if str(info.get("severity") or "").lower() == "info":
            continue
        host = str(obj.get("host") or obj.get("matched-at") or "")
        host_key = host.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
        template_id = str(obj.get("template-id") or "nuclei")
        matcher = str(obj.get("matcher-name") or "")
        fid = hashlib.sha256(f"{host}|{template_id}|{matcher}".encode()).hexdigest()[:48]
        title = str(info.get("name") or template_id)[:500]
        desc = str(info.get("description") or "").strip()
        summary = desc[:1200] if desc else f"Scan detected a potential issue on {host_key}."
        findings.append(
            {
                "external_finding_id": fid,
                "title": title,
                "severity": sev,
                "cve_id": None,
                "asset_hostname": host_to_asset.get(host_key),
                "customer_safe_summary": summary[:5000],
                "remediation_summary": (
                    "Review with your IT team and apply vendor updates or configuration hardening."
                )[:4000],
                "internal_notes": f"source=nuclei template={template_id} host={host}"[:10000],
                "recommendation_customer_visible": False,
            }
        )
    return findings


def _post_findings(tenant: str, findings: List[dict]) -> None:
    for i in range(0, len(findings), 100):
        chunk = findings[i : i + 100]
        _api(
            "POST",
            "/integrations/vuln/sync",
            {
                "tenant_short_code": tenant,
                "source_platform": "nuclei",
                "findings": chunk,
            },
        )


def main() -> int:
    if not Path(KEY_FILE).is_file():
        print(f"Missing scanner key file: {KEY_FILE}", file=sys.stderr)
        return 1
    if not Path(NUCLEI_BIN).is_file():
        print(f"Missing nuclei binary: {NUCLEI_BIN}", file=sys.stderr)
        return 1

    try:
        plan = _api("GET", "/integrations/vuln/scan-plan")
    except urllib.error.HTTPError as e:
        print(f"scan-plan failed: {e}", file=sys.stderr)
        return 1

    tenants = plan.get("tenants") or []
    if not tenants:
        print("No tenants due for scan.")
        return 0

    for entry in tenants:
        short = entry["tenant_short_code"]
        targets = entry.get("targets") or []
        target_lines = [t["target"] for t in targets if t.get("target")]
        if not target_lines:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            target_file = Path(tmp) / "targets.txt"
            jsonl_file = Path(tmp) / "out.jsonl"
            target_file.write_text("\n".join(target_lines) + "\n", encoding="utf-8")
            cmd = [
                NUCLEI_BIN,
                "-ud",
                NUCLEI_TEMPLATES,
                "-l",
                str(target_file),
                "-severity",
                SEVERITIES,
                "-jsonl",
                "-silent",
                "-no-color",
                "-o",
                str(jsonl_file),
            ]
            subprocess.run(cmd, check=False, timeout=3600)
            raw = jsonl_file.read_text(encoding="utf-8", errors="replace")
        findings = _normalize_jsonl(raw, short, targets)
        if findings:
            _post_findings(short, findings)
            print(f"tenant={short} synced_findings={len(findings)}")
        else:
            print(f"tenant={short} synced_findings=0")
        _api("POST", f"/integrations/vuln/scan-complete/{short}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
