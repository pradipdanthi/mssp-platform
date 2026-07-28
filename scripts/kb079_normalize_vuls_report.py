#!/usr/bin/env python3
"""KB-079: Vuls JSON report → vuln sync batches."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb079_vuln_scan_map import load_vuln_scan_targets  # noqa: E402


def _sev(score: float) -> str:
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    return "low"


def _server_tenant_map(tenants: Dict[str, Dict[str, Any]]) -> Dict[str, tuple[str, str | None]]:
    out: Dict[str, tuple[str, str | None]] = {}
    for short, cfg in tenants.items():
        asset = cfg.get("asset_hostname")
        for srv in cfg.get("vuls_servers") or []:
            name = str(srv.get("name") or "").strip()
            host = str(srv.get("host") or "").strip()
            if name:
                out[name] = (short, asset)
            if host:
                out[host] = (short, asset)
    return out


def normalize(report_path: Path, map_path: Path) -> dict:
    tenants = load_vuln_scan_targets(map_path)
    smap = _server_tenant_map(tenants)
    doc = json.loads(report_path.read_text(encoding="utf-8"))
    batches: Dict[str, List[dict]] = {}
    skipped = 0

    # Vuls report: { "servers": { "name": { "scannedCves": { "CVE-...": { ... } } } } }
    servers = doc.get("servers") or {}
    if not servers and isinstance(doc, dict):
        # Single-server export
        servers = {"default": doc}

    for server_name, server_body in servers.items():
        key = str(server_name)
        if key not in smap:
            skipped += 1
            continue
        tenant, asset_hostname = smap[key]
        scanned = (server_body or {}).get("scannedCves") or {}
        for cve_id, cve_body in scanned.items():
            if not str(cve_id).upper().startswith("CVE-"):
                skipped += 1
                continue
            score = 0.0
            if isinstance(cve_body, dict):
                for conf in cve_body.get("confidences") or []:
                    try:
                        score = max(score, float(conf.get("score") or 0))
                    except (TypeError, ValueError):
                        pass
            sev = _sev(score)
            title = f"Missing patch for {cve_id}"[:500]
            summary = (
                f"Host package analysis found {cve_id} on {key}. "
                "Apply vendor security updates for affected packages."
            )
            fid = hashlib.sha256(f"{key}|{cve_id}".encode()).hexdigest()[:48]
            batches.setdefault(tenant, []).append(
                {
                    "external_finding_id": fid,
                    "title": title,
                    "severity": sev,
                    "cve_id": cve_id[:64],
                    "nvt_oid": None,
                    "asset_hostname": asset_hostname,
                    "customer_safe_summary": summary[:5000],
                    "remediation_summary": (
                        "Install security updates from your OS vendor and reboot if required. "
                        "Your MSSP can help validate patching windows."
                    )[:4000],
                    "internal_notes": f"source=vuls server={key}"[:10000],
                    "create_recommendation": None,
                    "recommendation_customer_visible": False,
                }
            )

    return {
        "source_platform": "vuls",
        "batches": [{"tenant_short_code": t, "findings": f} for t, f in sorted(batches.items())],
        "stats": {
            "tenants": len(batches),
            "findings": sum(len(v) for v in batches.values()),
            "skipped": skipped,
        },
    }


def main() -> None:
    if len(sys.argv) != 4:
        print(
            "usage: kb079_normalize_vuls_report.py <report.json> <vuln_scan_targets.yml> <out.json>",
            file=sys.stderr,
        )
        raise SystemExit(2)
    out = normalize(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(out), encoding="utf-8")
    print(
        f"Normalized vuls findings={out['stats']['findings']} "
        f"tenants={out['stats']['tenants']} skipped={out['stats']['skipped']}"
    )


if __name__ == "__main__":
    main()
