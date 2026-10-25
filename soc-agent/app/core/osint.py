"""Free-tier OSINT lookups (no paid feeds required)."""

from __future__ import annotations

import os
from typing import Any

import httpx


def lookup_ip(ip: str | None) -> dict[str, Any]:
    if not ip:
        return {}
    out: dict[str, Any] = {"ip": ip, "sources": []}

    # AlienVault OTX (no key required for indicator page API in many lab setups;
    # if key present, use authenticated endpoint)
    otx_key = os.environ.get("OTX_API_KEY", "")
    try:
        headers = {"X-OTX-API-KEY": otx_key} if otx_key else {}
        with httpx.Client(timeout=8.0) as client:
            r = client.get(
                f"https://otx.alienvault.com/api/v1/indicators/IPv4/{ip}/general",
                headers=headers,
            )
            if r.status_code == 200:
                data = r.json()
                pulse = data.get("pulse_info") or {}
                out["sources"].append(
                    {
                        "name": "otx",
                        "pulse_count": pulse.get("count"),
                        "reputation": data.get("reputation"),
                        "validation": data.get("validation"),
                    }
                )
    except Exception as exc:  # noqa: BLE001
        out["sources"].append({"name": "otx", "error": str(exc)[:120]})

    # AbuseIPDB — only if free API key configured
    abuse_key = os.environ.get("ABUSEIPDB_API_KEY", "")
    if abuse_key:
        try:
            with httpx.Client(timeout=8.0) as client:
                r = client.get(
                    "https://api.abuseipdb.com/api/v2/check",
                    params={"ipAddress": ip, "maxAgeInDays": 90},
                    headers={"Key": abuse_key, "Accept": "application/json"},
                )
                if r.status_code == 200:
                    d = (r.json().get("data") or {})
                    out["sources"].append(
                        {
                            "name": "abuseipdb",
                            "abuse_confidence": d.get("abuseConfidenceScore"),
                            "total_reports": d.get("totalReports"),
                            "usage_type": d.get("usageType"),
                            "isp": d.get("isp"),
                        }
                    )
                else:
                    out["sources"].append(
                        {"name": "abuseipdb", "error": f"http_{r.status_code}"}
                    )
        except Exception as exc:  # noqa: BLE001
            out["sources"].append({"name": "abuseipdb", "error": str(exc)[:120]})
    else:
        out["sources"].append({"name": "abuseipdb", "skipped": "no_ABUSEIPDB_API_KEY"})

    return out


def enrich_osint(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_ip": lookup_ip(alert.get("source_ip") or alert.get("src_ip")),
        "destination_ip": lookup_ip(
            alert.get("destination_ip") or alert.get("dst_ip")
        ),
    }
