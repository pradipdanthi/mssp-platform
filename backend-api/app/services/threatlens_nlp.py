"""Kevantic ThreatLens — AI-assisted IOC extraction from advisories (regex + heuristics)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set
from urllib.parse import urlparse

_IP_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
)
_DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,24})\b",
    re.I,
)
_MD5_RE = re.compile(r"\b[a-fA-F0-9]{32}\b")
_SHA1_RE = re.compile(r"\b[a-fA-F0-9]{40}\b")
_SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.I)
_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
_DEFANG_MAP = str.maketrans({"[": "", "]": "", "(": "", ")": ""})

_NOISE_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "localhost",
    "github.com",
    "microsoft.com",
    "google.com",
    "amazon.com",
    "cloudflare.com",
}


def _defang(text: str) -> str:
    return (
        text.replace("[.]", ".")
        .replace("(.)", ".")
        .replace("[://]", "://")
        .replace("hxxp://", "http://")
        .replace("hxxps://", "https://")
        .translate(_DEFANG_MAP)
    )


def extract_iocs(
    text: str = "",
    *,
    url: str | None = None,
    source_label: str = "advisory",
) -> Dict[str, Any]:
    """Extract IPs, domains, hashes, CVEs, and URLs from free text (or fetched URL body)."""
    body = text or ""
    fetched = False
    if url and not body.strip():
        body = _fetch_url_text(url)
        fetched = True
    elif url and body.strip():
        body = f"{body}\n{url}"

    cleaned = _defang(body)
    ips = sorted(set(_IP_RE.findall(cleaned)))
    cves = sorted({c.upper() for c in _CVE_RE.findall(cleaned)})
    urls = sorted({u.rstrip(".,);]") for u in _URL_RE.findall(cleaned)})[:50]

    sha256 = sorted(set(_SHA256_RE.findall(cleaned)))
    sha1 = sorted(set(_SHA1_RE.findall(cleaned)) - set(sha256))
    # Avoid treating SHA256 prefixes as MD5
    md5_raw = set(_MD5_RE.findall(cleaned))
    md5 = sorted(md5_raw - {h[:32] for h in sha256} - {h[:32] for h in sha1})

    domains: Set[str] = set()
    for d in _DOMAIN_RE.findall(cleaned):
        low = d.lower().rstrip(".")
        if low in _NOISE_DOMAINS:
            continue
        if any(low.endswith(f".{n}") for n in ("png", "jpg", "css", "js")):
            continue
        domains.add(low)
    for u in urls:
        try:
            host = urlparse(u).hostname
            if host and host.lower() not in _NOISE_DOMAINS:
                domains.add(host.lower())
        except Exception:
            pass

    iocs: List[Dict[str, str]] = []
    for v in ips:
        iocs.append({"type": "IP", "value": v})
    for v in sorted(domains):
        iocs.append({"type": "DOMAIN", "value": v})
    for v in sha256:
        iocs.append({"type": "HASH_SHA256", "value": v.lower()})
    for v in sha1:
        iocs.append({"type": "HASH_SHA1", "value": v.lower()})
    for v in md5:
        iocs.append({"type": "HASH_MD5", "value": v.lower()})
    for v in cves:
        iocs.append({"type": "CVE", "value": v})
    for v in urls:
        iocs.append({"type": "URL", "value": v})

    flat_values = [i["value"] for i in iocs if i["type"] != "URL"]
    return {
        "engine": "Kevantic ThreatLens",
        "source": source_label,
        "url_fetched": fetched,
        "counts": {
            "ips": len(ips),
            "domains": len(domains),
            "hashes": len(sha256) + len(sha1) + len(md5),
            "cves": len(cves),
            "urls": len(urls),
            "total": len(iocs),
        },
        "iocs": iocs,
        "ioc_values": flat_values,
    }


def _fetch_url_text(url: str, timeout: float = 8.0) -> str:
    from urllib.request import Request, urlopen

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    req = Request(url, headers={"User-Agent": "Kevantic-ThreatLens/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator-controlled SOC URL
            raw = resp.read(500_000)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "pdf" in ctype or raw[:4] == b"%PDF":
                # Lightweight PDF text scrape (ASCII strings only — no PDF parser dep)
                text = re.sub(rb"[^\x20-\x7e\n\r\t]+", b" ", raw).decode("latin-1", "ignore")
                return text[:200_000]
            return raw.decode("utf-8", "ignore")[:200_000]
    except Exception:
        return ""
