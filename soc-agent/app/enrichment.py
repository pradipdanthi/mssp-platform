"""Enrichment: reverse DNS, IP reputation heuristics, MITRE ATT&CK mapping."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any

# Lab / RFC1918 safe lists + known "benign" demo sources
BENIGN_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
]

# Synthetic / documented malicious indicators for lab triage demos
MALICIOUS_IPS = {
    "198.51.100.66",  # TEST-NET-2 C2 stand-in
    "203.0.113.50",  # TEST-NET-3 payload host
}
MALICIOUS_DOMAINS = {
    "evil-c2.example",
    "malware-drop.example",
    "update-secure-login.example",
}

# Keyword → MITRE technique
MITRE_RULES: list[tuple[list[str], str, str]] = [
    (["brute", "failed password", "authentication failure", "ssh"], "T1110", "Brute Force"),
    (["c2", "beacon", "command and control", "cobalt"], "T1071", "Application Layer Protocol"),
    (["payload", "malware", "ransomware", "encrypt"], "T1486", "Data Encrypted for Impact"),
    (["lateral", "smb", "psexec", "wmi"], "T1021", "Remote Services"),
    (["exfil", "data transfer", "upload"], "T1041", "Exfiltration Over C2 Channel"),
    (["phishing", "credential harvest"], "T1566", "Phishing"),
    (["scan", "portscan", "nmap"], "T1046", "Network Service Discovery"),
]


def _ptr(ip: str) -> str | None:
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return None
    try:
        socket.setdefaulttimeout(1.5)
        name, _, _ = socket.gethostbyaddr(ip)
        return name
    except Exception:
        return None


def reputation(ip: str | None, domain: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ip": ip,
        "domain": domain,
        "classification": "unknown",
        "reasons": [],
        "ptr": None,
    }
    if domain and domain.lower().rstrip(".") in MALICIOUS_DOMAINS:
        result["classification"] = "malicious"
        result["reasons"].append(f"domain_blocklist:{domain}")
    if ip:
        result["ptr"] = _ptr(ip)
        if ip in MALICIOUS_IPS:
            result["classification"] = "malicious"
            result["reasons"].append("ip_blocklist")
        else:
            try:
                addr = ipaddress.ip_address(ip)
                if any(addr in net for net in BENIGN_NETWORKS):
                    if result["classification"] != "malicious":
                        result["classification"] = "benign_local"
                        result["reasons"].append("private_rfc1918")
            except ValueError:
                result["reasons"].append("invalid_ip")
    if result["classification"] == "unknown" and not result["reasons"]:
        result["classification"] = "suspicious_unlisted"
        result["reasons"].append("no_reputation_hit")
    return result


def mitre_map(title: str, description: str, tags: list[str] | None = None) -> list[dict[str, str]]:
    blob = " ".join([title or "", description or "", " ".join(tags or [])]).lower()
    hits: list[dict[str, str]] = []
    for keywords, tid, name in MITRE_RULES:
        if any(k in blob for k in keywords):
            hits.append({"technique_id": tid, "technique_name": name})
    return hits


def enrich_alert(alert: dict[str, Any]) -> dict[str, Any]:
    src = alert.get("source_ip") or alert.get("src_ip")
    dst = alert.get("destination_ip") or alert.get("dst_ip")
    domain = alert.get("domain") or alert.get("hostname")
    title = str(alert.get("title") or alert.get("rule") or "")
    desc = str(alert.get("description") or alert.get("raw_summary") or "")
    tags = alert.get("tags") if isinstance(alert.get("tags"), list) else []

    src_rep = reputation(src, domain if isinstance(domain, str) else None)
    dst_rep = reputation(dst, None) if dst else None
    mitre = mitre_map(title, desc, tags)

    return {
        "source_reputation": src_rep,
        "destination_reputation": dst_rep,
        "mitre": mitre,
        "enriched_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
