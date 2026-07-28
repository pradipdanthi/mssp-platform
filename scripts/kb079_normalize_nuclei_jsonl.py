#!/usr/bin/env python3
"""KB-079: Nuclei JSONL → vuln sync batches (tenant-scoped)."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb079_vuln_scan_map import load_vuln_scan_targets

_CVE_RE = re.compile(r"CVE-\d{4}-\d+", re.I)


def _severity(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in ("critical", "high", "medium", "low"):
        return s
    if s in ("info", "unknown"):
        return "low"
    return "low"


def _host_from_line(obj: dict) -> str:
    for key in ("host", "matched-at", "ip", "url"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _extract_host_key(host: str) -> str:
    m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", host)
    if m:
        return m.group(1)
    host = host.replace("https://", "").replace("http://", "")
    return host.split("/")[0].split(":")[0].strip()


def _cve_from_info(info: dict) -> str | None:
    if not info:
        return None
    classification = info.get("classification") or {}
    cve = classification.get("cve-id")
    if isinstance(cve, list) and cve:
        return str(cve[0])[:64]
    if isinstance(cve, str) and cve.strip():
        return cve.split(",")[0].strip()[:64]
    for tag in info.get("tags") or []:
        if isinstance(tag, str) and tag.upper().startswith("CVE-"):
            return tag[:64]
    text = json.dumps(info)
    m = _CVE_RE.search(text)
    return m.group(0).upper() if m else None


def _finding_id(host: str, template_id: str, matcher: str) -> str:
    base = f"{host}|{template_id}|{matcher}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:48]


def _target_index(tenants: Dict[str, Dict[str, Any]]) -> Dict[str, tuple[str, str | None]]:
    """Map host key → (tenant_short_code, asset_hostname)."""
    index: Dict[str, tuple[str, str | None]] = {}
    for short, cfg in tenants.items():
        asset = cfg.get("asset_hostname")
        for t in cfg.get("nuclei_targets") or []:
            key = _extract_host_key(str(t))
            if key:
                index[key] = (short, asset)
    return index


def normalize(jsonl_path: Path, map_path: Path) -> dict:
    tenants = load_vuln_scan_targets(map_path)
    index = _target_index(tenants)
    batches: Dict[str, List[dict]] = {}
    skipped = 0
    for line in jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        info = obj.get("info") or {}
        sev = _severity(str(info.get("severity") or obj.get("severity") or "low"))
        if sev == "low" and str(info.get("severity") or "").lower() == "info":
            skipped += 1
            continue
        host = _host_from_line(obj)
        host_key = _extract_host_key(host)
        if host_key not in index:
            skipped += 1
            continue
        tenant, asset_hostname = index[host_key]
        template_id = str(obj.get("template-id") or obj.get("templateID") or "nuclei")
        matcher = str(obj.get("matcher-name") or obj.get("type") or "")
        title = str(info.get("name") or template_id or "Security finding")[:500]
        desc = str(info.get("description") or "").strip()
        summary = (
            desc[:1200]
            if desc
            else f"Our vulnerability scan detected a potential issue affecting {host_key}."
        )
        remediation = (
            "Review the finding with your IT team and apply vendor patches or configuration "
            "hardening. Contact your MSSP if you need help prioritizing remediation."
        )
        cve = _cve_from_info(info)
        finding = {
            "external_finding_id": _finding_id(host, template_id, matcher),
            "title": title,
            "severity": sev,
            "cve_id": cve,
            "nvt_oid": None,
            "asset_hostname": asset_hostname,
            "customer_safe_summary": summary[:5000],
            "remediation_summary": remediation[:4000],
            "internal_notes": f"source=nuclei template={template_id} host={host}"[:10000],
            "create_recommendation": None,
            "recommendation_customer_visible": False,
        }
        batches.setdefault(tenant, []).append(finding)

    return {
        "source_platform": "nuclei",
        "batches": [
            {"tenant_short_code": t, "findings": f} for t, f in sorted(batches.items())
        ],
        "stats": {
            "tenants": len(batches),
            "findings": sum(len(v) for v in batches.values()),
            "skipped": skipped,
        },
    }


def main() -> None:
    if len(sys.argv) != 4:
        print(
            "usage: kb079_normalize_nuclei_jsonl.py <nuclei.jsonl> <vuln_scan_targets.yml> <out.json>",
            file=sys.stderr,
        )
        raise SystemExit(2)
    out = normalize(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(out), encoding="utf-8")
    print(
        f"Normalized nuclei findings={out['stats']['findings']} "
        f"tenants={out['stats']['tenants']} skipped={out['stats']['skipped']}"
    )


if __name__ == "__main__":
    main()
