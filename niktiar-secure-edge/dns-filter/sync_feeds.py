#!/usr/bin/env python3
"""
NikTiar™ DNS Filter — download category feeds and rebuild Blocky block groups.

Writes:
  /runtime/dns-feeds/<category>.txt   # one domain per line
  /runtime/dns-feeds/manifest.json
  /runtime/dns-filter/config.yml      # Blocky config
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Set
from urllib.parse import urlparse

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parent
RUNTIME = Path(os.getenv("RUNTIME_DIR") or "/runtime")
FEEDS_DIR = RUNTIME / "dns-feeds"
FILTER_DIR = RUNTIME / "dns-filter"
FEEDS_YAML = Path(os.getenv("DNS_FEEDS_YAML") or (ROOT / "feeds.yaml"))
CATS_YAML = Path(os.getenv("DNS_CATEGORIES_YAML") or (ROOT / "categories.yaml"))
UPSTREAM_DNS = os.getenv("NIKTIAR_DNS_UPSTREAM", "1.1.1.1,8.8.8.8")
LISTEN_ADDR = os.getenv("NIKTIAR_DNS_LISTEN", "0.0.0.0")
SINKHOLE = os.getenv("NIKTIAR_DNS_SINKHOLE", "0.0.0.0")

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
)


def load_yaml(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml:
        return yaml.safe_load(text) or {}
    # Minimal fallback if PyYAML missing — not expected in container
    raise RuntimeError("PyYAML required for dns-filter sync")


def normalize_domain(line: str) -> str | None:
    s = (line or "").strip().lower()
    if not s or s.startswith("#") or s.startswith("!"):
        return None
    # hosts format: 0.0.0.0 domain  OR  127.0.0.1 domain
    if s[0].isdigit() or s.startswith("::"):
        parts = s.split()
        if len(parts) >= 2:
            s = parts[1]
        else:
            return None
    # OISD wild: *.example.com → example.com (Blocky uses exact + optional wildcards separately)
    if s.startswith("*."):
        s = s[2:]
    s = s.strip(".")
    if s.endswith(".local") or s.endswith(".onion") or s in ("localhost", "broadcasthost"):
        return None
    try:
        ipaddress.ip_address(s)
        return None
    except ValueError:
        pass
    if not DOMAIN_RE.match(s):
        return None
    # Require at least one alpha label (drops pure-numeric IP-like leftovers)
    if not re.search(r"[a-z]", s):
        return None
    return s


def http_get(url: str, api_key: str | None = None, timeout: int = 120) -> str:
    headers = {"User-Agent": "NikTiar-DNS-Filter/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_list(text: str, fmt: str) -> Set[str]:
    out: Set[str] = set()
    if fmt == "niktiair_json":
        data = json.loads(text)
        cats = data.get("categories") or {}
        for _cat, domains in cats.items():
            for d in domains or []:
                nd = normalize_domain(str(d))
                if nd:
                    out.add(nd)
        return out
    if fmt == "ransomwatch_json":
        data = json.loads(text)
        for group in data or []:
            for loc in (group or {}).get("locations") or []:
                for key in ("fqdn", "host", "domain"):
                    nd = normalize_domain(str(loc.get(key) or ""))
                    if nd:
                        out.add(nd)
                for _k, v in (loc or {}).items():
                    if isinstance(v, str) and v.startswith("http"):
                        try:
                            h = (urlparse(v).hostname or "").lower()
                            nd = normalize_domain(h)
                            if nd:
                                out.add(nd)
                        except Exception:  # noqa: BLE001
                            pass
        return out
    for line in text.splitlines():
        nd = normalize_domain(line)
        if nd:
            out.add(nd)
    return out


def resolve_provider_url(prov: Dict[str, Any]) -> str | None:
    url = (prov.get("url") or "").strip()
    if url:
        return url
    env_name = (prov.get("url_env") or "").strip()
    if env_name:
        u = (os.getenv(env_name) or "").strip()
        if u:
            return u
    # ThreatFox: build hostfile URL from auth key when set
    key_env = (prov.get("api_key_env") or "").strip()
    if key_env == "NIKTIAR_THREATFOX_AUTH_KEY" or "threatfox" in (prov.get("label") or "").lower():
        key = (os.getenv(key_env) or "").strip() if key_env else ""
        if key:
            return f"https://threatfox-api.abuse.ch/v2/files/exports/{key}/hostfile"
    return None


def resolve_provider_body(prov: Dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (body, source_label) or (None, skip_reason)."""
    file_name = (prov.get("file") or "").strip()
    if file_name:
        path = ROOT / file_name
        if not path.is_file():
            return None, f"missing_file:{file_name}"
        return path.read_text(encoding="utf-8", errors="replace"), f"file:{file_name}"
    url = resolve_provider_url(prov)
    if not url:
        return None, "url_not_configured"
    key_env = (prov.get("api_key_env") or "").strip()
    api_key = os.getenv(key_env) if key_env else None
    return http_get(url, api_key=api_key), url.split("?")[0]


def sync_once() -> Dict[str, Any]:
    FEEDS_DIR.mkdir(parents=True, exist_ok=True)
    FILTER_DIR.mkdir(parents=True, exist_ok=True)
    feeds_cfg = load_yaml(FEEDS_YAML)
    cats_cfg = load_yaml(CATS_YAML)
    category_ids = list((cats_cfg.get("categories") or {}).keys())
    by_cat: Dict[str, Set[str]] = {c: set() for c in category_ids}
    # Always ensure custom file exists (operator + API append)
    custom_path = FEEDS_DIR / "custom.txt"
    if custom_path.exists():
        by_cat.setdefault("custom", set()).update(
            d for d in (normalize_domain(x) for x in custom_path.read_text().splitlines()) if d
        )
    else:
        custom_path.write_text("# NikTiar custom domain blocklist (one domain per line)\n", encoding="utf-8")

    report: Dict[str, Any] = {"providers": {}, "categories": {}, "ts": int(time.time())}
    sinkhole = (feeds_cfg.get("sinkhole_ip") or SINKHOLE).strip() or "0.0.0.0"

    for pid, prov in (feeds_cfg.get("providers") or {}).items():
        url = resolve_provider_url(prov)
        has_file = bool((prov.get("file") or "").strip())
        # Auto-enable commercial / ThreatFox hooks when URL or auth key is present
        enabled = bool(prov.get("enabled"))
        if not enabled and (url or has_file) and (
            (prov.get("url_env") or "").strip() or (prov.get("api_key_env") or "").strip()
        ):
            enabled = True
        if not enabled:
            report["providers"][pid] = {"skipped": True, "reason": "disabled"}
            continue
        fmt = (prov.get("format") or "domains").lower()
        try:
            body, source = resolve_provider_body(prov)
            if body is None:
                report["providers"][pid] = {"skipped": True, "reason": source or "no_source"}
                continue
            domains = parse_list(body, fmt)
            for cat in prov.get("categories") or []:
                if cat not in by_cat:
                    by_cat[cat] = set()
                if fmt == "niktiair_json":
                    data = json.loads(body)
                    for d in (data.get("categories") or {}).get(cat) or []:
                        nd = normalize_domain(str(d))
                        if nd:
                            by_cat[cat].add(nd)
                else:
                    by_cat[cat].update(domains)
            report["providers"][pid] = {"ok": True, "domains": len(domains), "source": source}
        except Exception as exc:  # noqa: BLE001
            report["providers"][pid] = {"ok": False, "error": str(exc)[:240]}

    # Policy file: which categories are enforced (from edge dns policy).
    # Default = critical threat cats only (not adult/social/ads until operator opts in).
    policy_path = FILTER_DIR / "policy.json"
    enabled_cats = {"malware", "phishing", "ransomware", "cryptomining", "custom"}
    if policy_path.exists():
        try:
            pol = json.loads(policy_path.read_text(encoding="utf-8"))
            if pol.get("enabled") is False:
                enabled_cats = set()
            elif isinstance(pol.get("enabled_categories"), list) and pol["enabled_categories"]:
                enabled_cats = set(str(c) for c in pol["enabled_categories"])
            # Merge API custom domains
            for d in pol.get("custom_block_domains") or []:
                nd = normalize_domain(str(d))
                if nd:
                    by_cat.setdefault("custom", set()).add(nd)
            for d in pol.get("custom_allow_domains") or []:
                nd = normalize_domain(str(d))
                if nd:
                    for cat in list(by_cat.keys()):
                        by_cat[cat].discard(nd)
        except Exception:  # noqa: BLE001
            pass

    # Write per-category lists
    for cat, domains in by_cat.items():
        path = FEEDS_DIR / f"{cat}.txt"
        lines = sorted(domains)
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        report["categories"][cat] = {"count": len(lines), "enforced": cat in enabled_cats}

    # Build Blocky (v0.24+) config — paths must be absolute (/…), not file: URLs
    # (Blocky prefixes file:// itself; "file:/path" becomes file://file:/path and fails).
    upstreams = [u.strip() for u in UPSTREAM_DNS.split(",") if u.strip()]
    blocking_lists: Dict[str, List[str]] = {}
    for cat in sorted(enabled_cats):
        f = FEEDS_DIR / f"{cat}.txt"
        if f.exists() and f.stat().st_size > 0:
            blocking_lists[f"niktiair_{cat}"] = [str(f)]

    blocky = {
        "ports": {
            "dns": f"{LISTEN_ADDR}:53",
            "http": "0.0.0.0:4000",
        },
        "upstreams": {"groups": {"default": upstreams}},
        "blocking": {
            "denylists": blocking_lists,
            "clientGroupsBlock": {"default": list(blocking_lists.keys())},
            "blockType": "zeroIp" if sinkhole in ("0.0.0.0", "::") else "nxDomain",
            "loading": {
                "strategy": "fast",
                "concurrency": 4,
                "maxErrorsPerSource": -1,
                "refreshPeriod": "6h",
            },
        },
        "caching": {"minTime": "5m", "maxTime": "30m", "prefetching": True},
        "log": {"level": "info"},
    }
    cfg_path = FILTER_DIR / "config.yml"
    if yaml:
        cfg_path.write_text(yaml.safe_dump(blocky, sort_keys=False), encoding="utf-8")
    else:
        cfg_path.write_text(json.dumps(blocky, indent=2), encoding="utf-8")

    # Domain blocklist for NikTiar WAF (Host header) — union of enforced cats
    waf_domains: Set[str] = set()
    for cat in enabled_cats:
        waf_domains.update(by_cat.get(cat) or [])
    # Cap WAF host list to keep Coraza reload sane (top malware/phish already covered by path filter)
    max_waf = int(os.getenv("NIKTIAR_DNS_WAF_DOMAIN_CAP", "5000"))
    waf_list = sorted(waf_domains)[:max_waf]
    (FEEDS_DIR / "waf_host_blocklist.txt").write_text("\n".join(waf_list) + "\n", encoding="utf-8")
    report["waf_host_blocklist"] = len(waf_list)
    report["blocking_groups"] = list(blocking_lists.keys())
    (FEEDS_DIR / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def loop() -> None:
    hours = 6.0
    try:
        hours = float(load_yaml(FEEDS_YAML).get("refresh_hours") or 6)
    except Exception:  # noqa: BLE001
        pass
    while True:
        try:
            rep = sync_once()
            print(json.dumps({"event": "dns_feed_sync", **{k: rep.get(k) for k in ("ts", "waf_host_blocklist", "blocking_groups")}}), flush=True)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"event": "dns_feed_sync_error", "error": str(exc)[:300]}), flush=True)
        time.sleep(max(300, int(hours * 3600)))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        print(json.dumps(sync_once(), indent=2))
    else:
        # Run once then loop
        try:
            print(json.dumps(sync_once(), indent=2), flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"initial sync failed: {exc}", flush=True)
        loop()
