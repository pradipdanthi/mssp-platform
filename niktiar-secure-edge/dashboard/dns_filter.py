"""NikTiar™ DNS Filter — policy, feed status, Host-header WAF domain blocklist."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

RUNTIME = Path(os.getenv("RUNTIME_DIR") or "/runtime")
FEEDS_DIR = RUNTIME / "dns-feeds"
FILTER_DIR = RUNTIME / "dns-filter"
POLICY_PATH = FILTER_DIR / "policy.json"
MANIFEST_PATH = FEEDS_DIR / "manifest.json"
WAF_LIST = FEEDS_DIR / "waf_host_blocklist.txt"
RULES_D = RUNTIME / "coraza-rules.d"
DNS_CONTAINER = os.getenv("DNS_FILTER_CONTAINER") or "niktiar-se-dns"
FEED_SYNC_CONTAINER = os.getenv("DNS_FEED_SYNC_CONTAINER") or "niktiar-se-dns-sync"

# Bundled taxonomy (also shipped under dns-filter/categories.yaml on the edge)
DEFAULT_CATEGORIES: Dict[str, Dict[str, str]] = {
    "malware": {"label": "Malware & C2", "hint": "Known malware droppers, botnet C2, and exploit kit domains.", "severity": "critical"},
    "phishing": {"label": "Phishing & fraud", "hint": "Credential-harvest and brand-impersonation domains.", "severity": "critical"},
    "ransomware": {"label": "Ransomware infrastructure", "hint": "Domains linked to ransomware operators and payment portals.", "severity": "critical"},
    "adult": {"label": "Adult content", "hint": "Adult / NSFW domains.", "severity": "medium"},
    "gambling": {"label": "Gambling", "hint": "Online gambling and betting domains.", "severity": "medium"},
    "social": {"label": "Social media", "hint": "Major social networks (optional workplace control).", "severity": "low"},
    "ads": {"label": "Advertising & trackers", "hint": "Ad networks and cross-site trackers.", "severity": "low"},
    "cryptomining": {"label": "Cryptomining", "hint": "Browser and botnet mining pools.", "severity": "high"},
    "proxy_vpn": {"label": "Anonymizers / proxies", "hint": "Public proxies and anonymizing gateways.", "severity": "medium"},
    "newly_registered": {"label": "Newly registered domains", "hint": "Very new domains often used in campaigns (when feed available).", "severity": "high"},
    "custom": {"label": "Custom blocklist", "hint": "Domains you add manually.", "severity": "high"},
}

DEFAULT_POLICY: Dict[str, Any] = {
    "enabled": True,
    "enabled_categories": [
        "malware",
        "phishing",
        "ransomware",
        "cryptomining",
        "custom",
    ],
    "custom_block_domains": [],
    "custom_allow_domains": [],
    "waf_host_block": True,
    "sinkhole_ip": "0.0.0.0",
    "listen_port": 53,
}

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
)


def normalize_domain(value: str) -> Optional[str]:
    s = (value or "").strip().lower().rstrip(".")
    if s.startswith("*."):
        s = s[2:]
    if not s or not DOMAIN_RE.match(s):
        return None
    return s


def default_policy() -> Dict[str, Any]:
    return deepcopy(DEFAULT_POLICY)


def load_policy() -> Dict[str, Any]:
    FILTER_DIR.mkdir(parents=True, exist_ok=True)
    if not POLICY_PATH.exists():
        pol = default_policy()
        save_policy(pol)
        return pol
    try:
        data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = default_policy()
    base = default_policy()
    base.update({k: v for k, v in data.items() if k in base or k in ("updated_at", "notes")})
    if isinstance(data.get("enabled_categories"), list):
        base["enabled_categories"] = [str(c) for c in data["enabled_categories"] if str(c) in DEFAULT_CATEGORIES]
    if isinstance(data.get("custom_block_domains"), list):
        base["custom_block_domains"] = [
            d for d in (normalize_domain(str(x)) for x in data["custom_block_domains"]) if d
        ]
    if isinstance(data.get("custom_allow_domains"), list):
        base["custom_allow_domains"] = [
            d for d in (normalize_domain(str(x)) for x in data["custom_allow_domains"]) if d
        ]
    return base


def save_policy(pol: Dict[str, Any]) -> None:
    FILTER_DIR.mkdir(parents=True, exist_ok=True)
    pol = dict(pol)
    pol["updated_at"] = int(time.time())
    POLICY_PATH.write_text(json.dumps(pol, indent=2), encoding="utf-8")
    # Mirror custom domains into feeds custom.txt for sync_feeds
    FEEDS_DIR.mkdir(parents=True, exist_ok=True)
    custom = sorted(set(pol.get("custom_block_domains") or []))
    (FEEDS_DIR / "custom.txt").write_text(
        "# NikTiar custom domain blocklist\n" + "\n".join(custom) + ("\n" if custom else ""),
        encoding="utf-8",
    )


def catalog() -> Dict[str, Any]:
    return {
        "categories": [
            {"id": k, "label": v["label"], "hint": v["hint"], "severity": v["severity"]}
            for k, v in DEFAULT_CATEGORIES.items()
        ],
        "help": {
            "dns_filter": (
                "NikTiar DNS Filter resolves queries for clients that use this edge as their DNS server. "
                "Blocked categories return a sinkhole answer so browsers never reach the bad domain."
            ),
            "url_vs_dns": (
                "NikTiar URL Filter inspects HTTP paths on traffic through the edge. "
                "NikTiar DNS Filter blocks entire domains at name-resolution time (stronger for malware/phishing)."
            ),
            "commercial_feed": (
                "Optional commercial category feed: set NIKTIAR_DNS_COMMERCIAL_FEED_URL and "
                "NIKTIAR_DNS_COMMERCIAL_API_KEY on the appliance (JSON categories map)."
            ),
            "waf_host": (
                "When WAF Host block is on, domains from enforced categories are also denied "
                "if a client requests them by Host header through NikTiar WAF."
            ),
        },
        "providers_note": "Open threat lists ship enabled; commercial feeds plug in via appliance env.",
    }


def feed_status() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "manifest": None,
        "policy": load_policy(),
        "category_files": {},
        "dns_container": DNS_CONTAINER,
        "sync_container": FEED_SYNC_CONTAINER,
    }
    if MANIFEST_PATH.exists():
        try:
            out["manifest"] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            out["manifest_error"] = str(exc)[:200]
    if FEEDS_DIR.exists():
        for p in sorted(FEEDS_DIR.glob("*.txt")):
            if p.name.startswith("waf_"):
                continue
            try:
                n = sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#"))
            except Exception:  # noqa: BLE001
                n = 0
            out["category_files"][p.stem] = n
    out["config_present"] = (FILTER_DIR / "config.yml").exists()
    out["waf_list_count"] = 0
    if WAF_LIST.exists():
        try:
            out["waf_list_count"] = sum(
                1 for line in WAF_LIST.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")
            )
        except Exception:  # noqa: BLE001
            pass
    return out


def _escape_rx_domain(d: str) -> str:
    return re.escape(d)


def write_waf_host_rules(pol: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compile Host-header domain denials into NikTiar WAF rules (no upstream brands in msgs)."""
    RULES_D.mkdir(parents=True, exist_ok=True)
    pol = pol or load_policy()
    lines = [
        "# Generated by NikTiar DNS Filter — Host header domain blocklist",
        f"# enabled={pol.get('enabled')} waf_host_block={pol.get('waf_host_block')}",
    ]
    rid = 1106000
    count = 0
    if pol.get("enabled", True) and pol.get("waf_host_block", True):
        domains: Set[str] = set()
        # Prefer compiled waf list from feed sync
        if WAF_LIST.exists():
            for line in WAF_LIST.read_text(encoding="utf-8").splitlines():
                nd = normalize_domain(line)
                if nd:
                    domains.add(nd)
        for d in pol.get("custom_block_domains") or []:
            nd = normalize_domain(str(d))
            if nd:
                domains.add(nd)
        for d in pol.get("custom_allow_domains") or []:
            nd = normalize_domain(str(d))
            if nd:
                domains.discard(nd)
        # Cap for rule-engine size (full DNS path still has the complete lists)
        max_n = int(os.getenv("NIKTIAR_DNS_WAF_DOMAIN_CAP", "5000"))
        ordered = sorted(domains)[:max_n]
        chunk = 40
        for i in range(0, len(ordered), chunk):
            part = ordered[i : i + chunk]
            # Match exact host or subdomain of listed domain
            alts = "|".join(_escape_rx_domain(d) for d in part)
            rx = f"(?i)^(?:{alts})$|\\.({alts})$"
            # Simplify: (?:^|\\.)domain(\\.|$ ) style per domain joined
            rx = "(?i)(?:^|\\.)(?:" + "|".join(_escape_rx_domain(d) for d in part) + ")$"
            lines.append(
                f'SecRule REQUEST_HEADERS:Host "@rx {rx}" '
                f'"id:{rid},phase:1,deny,status:403,log,msg:\'NikTiar DNS Filter blocked domain\'"'
            )
            rid += 1
            count += len(part)
    path = RULES_D / "11060-dns-host-block.conf"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for stale in ("91060-dns-host-block.conf",):
        p = RULES_D / stale
        if p.exists():
            p.unlink()
    return {"ok": True, "domains_compiled": count, "path": str(path)}


def trigger_feed_resync() -> Dict[str, Any]:
    """Ask the feed-sync container to run one sync (best-effort)."""
    try:
        r = subprocess.run(
            [
                "docker",
                "exec",
                FEED_SYNC_CONTAINER,
                "python",
                "-u",
                "sync_feeds.py",
                "--once",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        return {
            "ok": r.returncode == 0,
            "stdout": (r.stdout or "")[-800:],
            "stderr": (r.stderr or "")[-400:],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def reload_dns_engine() -> Dict[str, Any]:
    """Reload NikTiar DNS Filter runtime after config/list change."""
    # Distroless DNS runtime has no wget/curl — refresh via host-published API or restart.
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:4053/api/lists/refresh", timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")[:200]
            return {"ok": True, "method": "lists_refresh", "body": body}
    except Exception:  # noqa: BLE001
        pass
    try:
        r = subprocess.run(
            ["docker", "restart", DNS_CONTAINER],
            capture_output=True,
            text=True,
            timeout=45,
        )
        return {"ok": r.returncode == 0, "method": "restart", "stderr": (r.stderr or "")[-200:]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def apply_dns_filter(pol: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    pol = pol or load_policy()
    save_policy(pol)
    sync = trigger_feed_resync()
    waf = write_waf_host_rules(pol)
    dns = reload_dns_engine() if sync.get("ok") or (FILTER_DIR / "config.yml").exists() else {"ok": False, "skipped": True}
    return {"ok": True, "policy": pol, "waf": waf, "sync": sync, "dns_reload": dns}


def merge_into_edge_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure edge_config.json carries a dns_filter snapshot for portal visibility."""
    g = cfg.setdefault("global", {})
    g["dns_filter"] = load_policy()
    return cfg
