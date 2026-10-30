"""Free-tier OSINT lookups (no paid feeds required)."""

from __future__ import annotations

import ipaddress
import os
from typing import Any, Iterable

import httpx


class _Skip(Exception):
    pass


def lookup_ip(ip: str | None, providers: Iterable[str] = ("otx", "abuseipdb")) -> dict[str, Any]:
    if not ip:
        return {}
    allowed = set(providers)
    out: dict[str, Any] = {"ip": ip, "sources": []}

    # AlienVault OTX (no key required for indicator page API in many lab setups;
    # if key present, use authenticated endpoint)
    otx_key = os.environ.get("OTX_API_KEY", "")
    try:
        if "otx" not in allowed:
            raise _Skip
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
    except _Skip:
        pass
    except Exception as exc:  # noqa: BLE001
        out["sources"].append({"name": "otx", "error": str(exc)[:120]})

    # AbuseIPDB — only if free API key configured
    abuse_key = os.environ.get("ABUSEIPDB_API_KEY", "")
    if "abuseipdb" not in allowed:
        pass
    elif abuse_key:
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


_PROVIDER_FOR_SOURCE = {"otx": "otx", "abuseipdb": "abuseipdb"}


def _public(ip: str | None) -> bool:
    try:
        return bool(ip) and ipaddress.ip_address(str(ip)).is_global
    except ValueError:
        return False


def enrich_osint(alert: dict[str, Any]) -> dict[str, Any]:
    """Reputation lookups only where the control plane says this customer authorised them.

    No policy in the request means no lookups: an address from a customer's network is
    customer data, and an allow-list of reachable sites is not that customer's consent.
    """
    policy = ((alert.get("raw") or {}).get("research_policy") or {}) if isinstance(alert.get("raw"), dict) else {}
    providers = {p for p in (policy.get("ip_reputation") or []) if p in _PROVIDER_FOR_SOURCE}
    out: dict[str, Any] = {}
    for key, alt in (("source_ip", "src_ip"), ("destination_ip", "dst_ip")):
        ip = alert.get(key) or alert.get(alt)
        if not ip:
            out[key] = {}
        elif not providers:
            out[key] = {"skipped": "customer_has_not_authorised_ip_reputation"}
        elif not _public(ip):
            out[key] = {"skipped": "not_a_public_address"}
        else:
            out[key] = lookup_ip(ip, providers)
    return out
