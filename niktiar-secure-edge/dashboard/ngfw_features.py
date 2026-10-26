"""
NikTiar Secure Edge — Next-Generation Firewall (NGFW) feature pack.

Enterprise L7 firewall controls compiled into NikTiar WAF / Edge Engine rules:
  • Ordered firewall policies (allow / deny / challenge / log)
  • URL / category filtering
  • Application control (HTTP method + path profiles)
  • Geo / country block lists (header or CF-IPCountry style)
  • Address / URL objects (named reusable lists)
  • Real path rate limiting (edge IP rate counters)

Designed so the appliance dashboard can explain every control in plain English.
"""
from __future__ import annotations

import re
import secrets
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RULES_D = Path("/runtime/coraza-rules.d")
NGFW_CADDY = Path("/runtime/ngfw.caddy")

# Plain-English catalog — shown in the UI Help / Policy Builder.
URL_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "malware": {
        "label": "Malware & exploit kits",
        "hint": "Blocks known malware drop sites and exploit kit paths.",
        "patterns": [
            r"(?i)/(?:malware|exploit|payload|shell)\.php",
            r"(?i)\.exe(\?|$)",
            r"(?i)/(?:c99|r57|wso|b374k)\.php",
        ],
    },
    "phishing": {
        "label": "Phishing / credential traps",
        "hint": "Blocks fake login and credential-harvest paths.",
        "patterns": [
            r"(?i)/(?:login|signin|account).*(?:verify|secure|update)",
            r"(?i)/wp-login\.php",
            r"(?i)/(?:paypal|appleid|microsoft).*login",
        ],
    },
    "scanning": {
        "label": "Scanner & recon probes",
        "hint": "Blocks common vulnerability scanner and recon URLs.",
        "patterns": [
            r"(?i)/(?:phpmyadmin|pma|adminer)",
            r"(?i)/\.git(?:/|$)",
            r"(?i)/(?:actuator|solr|jenkins|manager/html)",
            r"(?i)/\.(?:env|aws|docker)",
        ],
    },
    "adult": {
        "label": "Adult content paths",
        "hint": "Blocks obvious adult-content path keywords (path-based only).",
        "patterns": [r"(?i)/(?:porn|xxx|adult-content)(/|$|\?)"],
    },
    "gambling": {
        "label": "Gambling paths",
        "hint": "Blocks gambling-related path keywords.",
        "patterns": [r"(?i)/(?:casino|betting|sportsbook)(/|$|\?)"],
    },
    "social": {
        "label": "Social media widgets",
        "hint": "Optional: block social share/embed endpoints on your sites.",
        "patterns": [
            r"(?i)/facebook\.com/tr",
            r"(?i)/(?:share|tweet)\?(?:.*url=)",
        ],
    },
    "crypto_mining": {
        "label": "Crypto mining scripts",
        "hint": "Blocks known cryptominer script paths.",
        "patterns": [
            r"(?i)coinhive",
            r"(?i)cryptonight",
            r"(?i)/lib/miner\.js",
        ],
    },
    "ransomware": {
        "label": "Ransomware staging / notes",
        "hint": "Blocks ransom-note filenames and common ransomware staging path keywords.",
        "patterns": [
            r"(?i)/(?:README_FOR_DECRYPT|HOW_TO_DECRYPT|DECRYPT_INSTRUCTIONS)",
            r"(?i)/(?:lockbit|blackcat|alphv|conti|play.?ransom|qilin|rhysida|akira)",
            r"(?i)\.(?:pdf|doc|docx)\.(?:exe|scr|js|vbs)(?:$|\?)",
        ],
    },
    "proxy_avoidance": {
        "label": "Proxy / anonymizer paths",
        "hint": "Blocks common proxy-avoidance and anonymizer URL patterns (NGFW URL Filtering style).",
        "patterns": [
            r"(?i)/(?:proxy|anonymizer|hide.?my|vpn.?gate)",
            r"(?i)(?:cgi-bin/nph-proxy|phproxy|glype)",
        ],
    },
    "dynamic_dns": {
        "label": "Dynamic DNS style hosts in path",
        "hint": "Blocks requests whose path embeds common dynamic-DNS provider names.",
        "patterns": [
            r"(?i)(?:duckdns|no-ip|dyndns|afraid\.org|hopto\.org|zapto\.org|sytes\.net)",
        ],
    },
    "parked": {
        "label": "Parked / placeholder abuse",
        "hint": "Blocks obvious parked-domain and placeholder abuse paths.",
        "patterns": [
            r"(?i)/(?:parking|sedoparking|godaddy.?parked)",
        ],
    },
}

APP_PROFILES: Dict[str, Dict[str, Any]] = {
    "web_browsing": {
        "label": "Web browsing (GET/HEAD)",
        "hint": "Normal page loads — usually Allow.",
        "methods": ["GET", "HEAD"],
        "path_rx": r".*",
    },
    "api": {
        "label": "API traffic",
        "hint": "JSON/API paths under /api — pair with rate limits.",
        "methods": ["GET", "POST", "PUT", "PATCH", "DELETE"],
        "path_rx": r"(?i)^/api(/|$)",
    },
    "login": {
        "label": "Login / auth",
        "hint": "Sign-in forms — protect with rate limit + Bot Fight.",
        "methods": ["GET", "POST"],
        "path_rx": r"(?i)/(?:login|signin|auth|oauth|token)(/|$|\?)",
    },
    "admin": {
        "label": "Admin panels",
        "hint": "Back-office paths — usually Deny from internet, Allow from office IPs.",
        "methods": ["GET", "POST", "PUT", "PATCH", "DELETE"],
        "path_rx": r"(?i)/(?:admin|wp-admin|dashboard|manage)(/|$)",
    },
    "file_upload": {
        "label": "File uploads",
        "hint": "Multipart POST uploads — inspect with WAF tightly.",
        "methods": ["POST", "PUT"],
        "path_rx": r"(?i)/(?:upload|media|files)(/|$)",
    },
    "graphql": {
        "label": "GraphQL",
        "hint": "GraphQL endpoints — enable GraphQL Guard in Enterprise.",
        "methods": ["POST", "GET"],
        "path_rx": r"(?i)/graphql(/|$)",
    },
}

DEFAULT_NGFW: Dict[str, Any] = {
    "enabled": True,
    "default_action": "allow",  # allow | deny — implicit last rule
    "address_objects": [
        {
            "id": "obj_any",
            "name": "Any",
            "type": "any",
            "values": [],
            "description": "Match every source IP.",
        },
        {
            "id": "obj_private",
            "name": "Private networks",
            "type": "cidr",
            "values": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.1"],
            "description": "RFC1918 + localhost — typical office/lab sources.",
        },
    ],
    "url_objects": [
        {
            "id": "url_admin",
            "name": "Admin paths",
            "patterns": [r"(?i)/(?:admin|wp-admin)(/|$)"],
            "description": "Common admin URL prefixes.",
        }
    ],
    "url_filter": {
        "enabled": True,
        "mode": "block",  # block | log
        "categories": ["malware", "phishing", "scanning", "crypto_mining", "ransomware"],
        "custom_block": [],  # extra regexes
        "custom_allow": [],  # exceptions (checked first)
    },
    "geo_block": {
        "enabled": False,
        "mode": "block",
        "countries": [],  # ISO 3166-1 alpha-2
        "header": "CF-IPCountry",  # or X-Country-Code if you front with another edge
        "description": "Block or log by country code in the request header.",
    },
    "policies": [
        {
            "id": "pol_allow_health",
            "name": "Allow health checks",
            "enabled": True,
            "priority": 10,
            "action": "allow",
            "source": "any",
            "zone": "*",
            "app": None,
            "methods": ["GET", "HEAD"],
            "path_contains": "/healthz",
            "description": "Let load balancers and monitors reach /healthz.",
        },
        {
            "id": "pol_block_scanners",
            "name": "Block scanner User-Agents",
            "enabled": True,
            "priority": 20,
            "action": "deny",
            "source": "any",
            "zone": "*",
            "ua_contains": ["sqlmap", "nikto", "masscan", "zgrab", "dirbuster"],
            "description": "Drop obvious attack tools before they hit the origin.",
        },
    ],
}


def merge_ngfw(cfg: Dict[str, Any]) -> Dict[str, Any]:
    g = cfg.setdefault("global", {})
    ngfw = g.get("ngfw")
    if not isinstance(ngfw, dict):
        g["ngfw"] = deepcopy(DEFAULT_NGFW)
    else:
        base = deepcopy(DEFAULT_NGFW)
        base.update({k: v for k, v in ngfw.items() if k not in ("policies", "address_objects", "url_objects")})
        for key in ("policies", "address_objects", "url_objects"):
            if isinstance(ngfw.get(key), list) and ngfw[key]:
                base[key] = ngfw[key]
            else:
                base[key] = deepcopy(DEFAULT_NGFW[key])
        if isinstance(ngfw.get("url_filter"), dict):
            uf = deepcopy(DEFAULT_NGFW["url_filter"])
            uf.update(ngfw["url_filter"])
            base["url_filter"] = uf
        if isinstance(ngfw.get("geo_block"), dict):
            geo = deepcopy(DEFAULT_NGFW["geo_block"])
            geo.update(ngfw["geo_block"])
            base["geo_block"] = geo
        g["ngfw"] = base
    # Ensure every zone has firewall + rate_limit + ngfw overlays
    for z in cfg.get("zones") or []:
        fw = z.setdefault("firewall", {})
        fw.setdefault("ip_allow", [])
        fw.setdefault("ip_block", [])
        fw.setdefault("ua_block", [])
        fw.setdefault("asn_block", [])
        fw.setdefault("countries_block", [])
        fw.setdefault("url_categories", [])
        fw.setdefault("url_custom_block", [])
        z.setdefault("rate_limit_rules", [])
        z.setdefault("ngfw_policies", [])  # zone-local extras
    return cfg


def catalog() -> Dict[str, Any]:
    return {
        "url_categories": [
            {"id": k, "label": v["label"], "hint": v["hint"]} for k, v in URL_CATEGORIES.items()
        ],
        "app_profiles": [
            {"id": k, "label": v["label"], "hint": v["hint"], "methods": v["methods"]}
            for k, v in APP_PROFILES.items()
        ],
        "actions": [
            {"id": "allow", "label": "Allow", "hint": "Let the request through to the origin."},
            {"id": "deny", "label": "Deny (block)", "hint": "Return HTTP 403 and log the hit."},
            {
                "id": "challenge",
                "label": "Challenge",
                "hint": "Show a browser check (503 challenge) before allowing access.",
            },
            {"id": "log", "label": "Log only", "hint": "Do not block — write a security log entry."},
            {
                "id": "rate_limit",
                "label": "Rate limit",
                "hint": "Throttle this traffic (use Rate Limiting rules for thresholds).",
            },
        ],
        "default_ngfw": deepcopy(DEFAULT_NGFW),
        "help": {
            "policy_order": (
                "Policies are evaluated from lowest priority number to highest. "
                "The first match wins. Put specific Allow rules above broad Deny rules."
            ),
            "url_filter": (
                "URL Filter checks the request path against category pattern lists "
                "(malware, phishing, scanners, …) plus your custom regexes. "
                "Allow-list exceptions are checked first."
            ),
            "objects": (
                "Address objects and URL objects are named lists you reuse in policies — "
                "like enterprise firewall address groups."
            ),
            "waf_vs_ngfw": (
                "NikTiar WAF looks inside requests for attacks (SQLi, XSS). "
                "NikTiar NGFW policies decide WHO can talk to WHICH site/path — the outer gate."
            ),
        },
    }


def _safe(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", (s or "")[:40])


def _esc_msg(s: str) -> str:
    return (s or "").replace("'", "")[:80]


def _action_secrule(action: str) -> str:
    a = (action or "deny").lower()
    if a == "allow":
        return "allow"
    if a == "log":
        return "pass,log"
    if a in ("challenge", "js_challenge"):
        return "deny,status:503"
    if a == "rate_limit":
        return "deny,status:429"
    return "deny,status:403"


def _normalize_host(h: Optional[str]) -> str:
    return (h or "").strip().lower().split(":")[0]


def _resolve_source_ips(ngfw: Dict[str, Any], source: str) -> Optional[List[str]]:
    """Return CIDR/IP list, empty list for 'any', None if unknown object."""
    src = (source or "any").strip()
    if not src or src.lower() in ("any", "*", "obj_any"):
        return []
    # Inline CIDR / IP
    if re.match(r"^[\d./]+$", src) or "," in src:
        return [p.strip() for p in src.split(",") if p.strip()]
    for obj in ngfw.get("address_objects") or []:
        if obj.get("id") == src or (obj.get("name") or "").lower() == src.lower():
            if (obj.get("type") or "") == "any":
                return []
            return [str(v).strip() for v in (obj.get("values") or []) if str(v).strip()]
    return [src]  # treat as literal IP/CIDR


def _write_url_filter(cfg: Dict[str, Any], lines: List[str], rid: int) -> int:
    ngfw = ((cfg.get("global") or {}).get("ngfw") or {})
    uf = ngfw.get("url_filter") or {}
    if not uf.get("enabled", True):
        lines.append("# URL Filter disabled")
        return rid

    mode = (uf.get("mode") or "block").lower()
    act = "pass,log" if mode == "log" else "deny,status:403"

    # Allow exceptions first
    for pat in uf.get("custom_allow") or []:
        pat = str(pat).strip()
        if not pat:
            continue
        lines.append(
            f'SecRule REQUEST_URI "@rx {pat}" '
            f'"id:{rid},phase:1,allow,nolog,msg:\'NikTiar URL allow exception\'"'
        )
        rid += 1

    cats = uf.get("categories") or []
    for cat in cats:
        meta = URL_CATEGORIES.get(str(cat))
        if not meta:
            continue
        for pat in meta.get("patterns") or []:
            lines.append(
                f'SecRule REQUEST_URI "@rx {pat}" '
                f'"id:{rid},phase:1,{act},log,msg:\'NikTiar URL Filter category={cat}\'"'
            )
            rid += 1

    for pat in uf.get("custom_block") or []:
        pat = str(pat).strip()
        if not pat:
            continue
        lines.append(
            f'SecRule REQUEST_URI "@rx {pat}" '
            f'"id:{rid},phase:1,{act},log,msg:\'NikTiar URL Filter custom\'"'
        )
        rid += 1

    # Per-zone URL overlays
    for z in cfg.get("zones") or []:
        host = _normalize_host(z.get("public_hostname"))
        if not host:
            continue
        fw = z.get("firewall") or {}
        for cat in fw.get("url_categories") or []:
            meta = URL_CATEGORIES.get(str(cat))
            if not meta:
                continue
            for pat in meta.get("patterns") or []:
                lines.append(
                    f'SecRule REQUEST_HEADERS:Host "@streq {host}" '
                    f'"id:{rid},phase:1,{act},log,chain,msg:\'NikTiar zone URL Filter {cat} host={host}\'"'
                )
                rid += 1
                lines.append(f'SecRule REQUEST_URI "@rx {pat}"')
                rid += 1
        for pat in fw.get("url_custom_block") or []:
            pat = str(pat).strip()
            if not pat:
                continue
            lines.append(
                f'SecRule REQUEST_HEADERS:Host "@streq {host}" '
                f'"id:{rid},phase:1,{act},log,chain,msg:\'NikTiar zone URL custom host={host}\'"'
            )
            rid += 1
            lines.append(f'SecRule REQUEST_URI "@rx {pat}"')
            rid += 1
    return rid


def _write_geo(cfg: Dict[str, Any], lines: List[str], rid: int) -> int:
    ngfw = ((cfg.get("global") or {}).get("ngfw") or {})
    geo = ngfw.get("geo_block") or {}
    if not geo.get("enabled"):
        return rid
    header = re.sub(r"[^A-Za-z0-9_-]", "", geo.get("header") or "CF-IPCountry") or "CF-IPCountry"
    countries = [str(c).strip().upper() for c in (geo.get("countries") or []) if str(c).strip()]
    if not countries:
        return rid
    mode = (geo.get("mode") or "block").lower()
    act = "pass,log" if mode == "log" else "deny,status:403"
    # Match if header equals any blocked country
    rx = "^(?:" + "|".join(re.escape(c) for c in countries) + ")$"
    lines.append(
        f'SecRule REQUEST_HEADERS:{header} "@rx {rx}" '
        f'"id:{rid},phase:1,{act},log,msg:\'NikTiar Geo block\'"'
    )
    rid += 1
    # Per-zone country lists
    for z in cfg.get("zones") or []:
        host = _normalize_host(z.get("public_hostname"))
        fw = z.get("firewall") or {}
        zc = [str(c).strip().upper() for c in (fw.get("countries_block") or []) if str(c).strip()]
        if not host or not zc:
            continue
        zrx = "^(?:" + "|".join(re.escape(c) for c in zc) + ")$"
        lines.append(
            f'SecRule REQUEST_HEADERS:Host "@streq {host}" '
            f'"id:{rid},phase:1,{act},log,chain,msg:\'NikTiar Geo zone host={host}\'"'
        )
        rid += 1
        lines.append(f'SecRule REQUEST_HEADERS:{header} "@rx {zrx}"')
        rid += 1
    return rid


def _write_policies(cfg: Dict[str, Any], lines: List[str], rid: int) -> int:
    ngfw = ((cfg.get("global") or {}).get("ngfw") or {})
    policies = list(ngfw.get("policies") or [])
    # Append zone-local policies
    for z in cfg.get("zones") or []:
        host = _normalize_host(z.get("public_hostname"))
        for p in z.get("ngfw_policies") or []:
            pp = dict(p)
            if host and not pp.get("zone"):
                pp["zone"] = host
            policies.append(pp)

    policies = [p for p in policies if p.get("enabled", True)]
    policies.sort(key=lambda p: int(p.get("priority") or 100))

    for pol in policies:
        name = _esc_msg(pol.get("name") or "policy")
        action = _action_secrule(str(pol.get("action") or "deny"))
        zone = (pol.get("zone") or "*").strip().lower()
        methods = [str(m).upper() for m in (pol.get("methods") or []) if str(m).strip()]
        path_contains = (pol.get("path_contains") or "").strip()
        path_rx = (pol.get("path_rx") or "").strip()
        ua_list = [str(u).strip() for u in (pol.get("ua_contains") or []) if str(u).strip()]
        app_id = pol.get("app")
        if app_id and app_id in APP_PROFILES:
            app = APP_PROFILES[app_id]
            if not methods:
                methods = list(app["methods"])
            if not path_rx:
                path_rx = app["path_rx"]

        source_ips = _resolve_source_ips(ngfw, str(pol.get("source") or "any"))

        # Build chain: Host → Method → Path → UA → IP → action on last
        chain_parts: List[Tuple[str, str]] = []
        if zone and zone not in ("*", "any", "all"):
            chain_parts.append(("REQUEST_HEADERS:Host", f"@streq {zone}"))
        if methods:
            meth_rx = "^(?:" + "|".join(re.escape(m) for m in methods) + ")$"
            chain_parts.append(("REQUEST_METHOD", f"@rx {meth_rx}"))
        if path_rx:
            chain_parts.append(("REQUEST_URI", f"@rx {path_rx}"))
        elif path_contains:
            esc = path_contains.replace("\\", "\\\\").replace('"', '\\"')
            chain_parts.append(("REQUEST_URI", f"@contains {esc}"))
        if ua_list:
            ua_rx = "(?i)(?:" + "|".join(re.escape(u) for u in ua_list) + ")"
            chain_parts.append(("REQUEST_HEADERS:User-Agent", f"@rx {ua_rx}"))
        if source_ips:  # empty = any
            # ipMatch supports comma-separated list in the WAF engine
            ip_arg = ",".join(source_ips)
            chain_parts.append(("REMOTE_ADDR", f"@ipMatch {ip_arg}"))

        if not chain_parts:
            lines.append(
                f'SecRule REMOTE_ADDR "@rx ." '
                f'"id:{rid},phase:1,{action},log,msg:\'NikTiar NGFW {name}\'"'
            )
            rid += 1
            continue

        n = len(chain_parts)
        for i, (var, op) in enumerate(chain_parts):
            if i == 0:
                if n == 1:
                    lines.append(
                        f'SecRule {var} "{op}" '
                        f'"id:{rid},phase:1,{action},log,msg:\'NikTiar NGFW {name}\'"'
                    )
                else:
                    lines.append(
                        f'SecRule {var} "{op}" '
                        f'"id:{rid},phase:1,{action},log,chain,msg:\'NikTiar NGFW {name}\'"'
                    )
            elif i < n - 1:
                lines.append(f'SecRule {var} "{op}" "chain"')
            else:
                lines.append(f'SecRule {var} "{op}"')
            rid += 1
    return rid


def _write_rate_limits(cfg: Dict[str, Any], lines: List[str], rid: int) -> int:
    """Real NikTiar Rate Limit rules using IP collections (Host + path scoped)."""
    lines.append("# NGFW rate limits — Host+path scoped IP counters")
    for z in cfg.get("zones") or []:
        host = _normalize_host(z.get("public_hostname"))
        if not host:
            continue
        for i, rl in enumerate(z.get("rate_limit_rules") or []):
            if rl.get("enabled") is False:
                continue
            path = (rl.get("path") or "/*").strip()
            if path.startswith("^") or ".*" in path:
                path_rx = path
            elif path.endswith("*"):
                path_rx = "^" + re.escape(path[:-1]) + ".*"
            else:
                path_rx = "^" + re.escape(path)
            reqs = max(1, int(rl.get("requests") or 100))
            period = max(1, int(rl.get("period") or 60))
            action = (rl.get("action") or "block").lower()
            deny = "deny,status:429" if action in ("block", "deny", "rate_limit") else "pass,log"
            var_name = f"rl_{_safe(host)}_{i}"
            name = _esc_msg(rl.get("name") or f"rl{i}")
            # Count: Host → path → setvar on last chained rule
            lines.append(
                f'SecRule REQUEST_HEADERS:Host "@streq {host}" '
                f'"id:{rid},phase:1,pass,nolog,chain,msg:\'NikTiar RL count {name}\'"'
            )
            rid += 1
            lines.append(
                f'SecRule REQUEST_URI "@rx {path_rx}" '
                f'"setvar:ip.{var_name}=+1,expirevar:ip.{var_name}={period}"'
            )
            rid += 1
            # Enforce: Host → path → IP counter
            lines.append(
                f'SecRule REQUEST_HEADERS:Host "@streq {host}" '
                f'"id:{rid},phase:1,{deny},log,chain,msg:\'NikTiar RL exceed {name} {reqs}/{period}s\'"'
            )
            rid += 1
            lines.append(f'SecRule REQUEST_URI "@rx {path_rx}" "chain"')
            rid += 1
            lines.append(f'SecRule IP:{var_name} "@gt {reqs}"')
            rid += 1
    return rid


def apply_ngfw(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Compile NGFW policies into NikTiar WAF rules.d + optional Caddy snippet."""
    merge_ngfw(cfg)
    RULES_D.mkdir(parents=True, exist_ok=True)
    ngfw = (cfg.get("global") or {}).get("ngfw") or {}
    lines: List[str] = [
        "# Generated by NikTiar NGFW — do not edit by hand",
        f"# enabled={ngfw.get('enabled', True)} default_action={ngfw.get('default_action')}",
    ]
    rid = 1110000
    if not ngfw.get("enabled", True):
        lines.append("# NGFW pack disabled")
        (RULES_D / "11050-ngfw.conf").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"ok": True, "rules": 0, "disabled": True}

    rid = _write_geo(cfg, lines, rid)
    rid = _write_url_filter(cfg, lines, rid)
    rid = _write_policies(cfg, lines, rid)
    rid = _write_rate_limits(cfg, lines, rid)

    # Default deny if configured
    if (ngfw.get("default_action") or "allow").lower() == "deny":
        lines.append(
            f'SecRule REMOTE_ADDR "@rx ." '
            f'"id:{rid},phase:1,deny,status:403,log,msg:\'NikTiar NGFW default deny\'"'
        )
        rid += 1

    (RULES_D / "11050-ngfw.conf").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Also replace old comment-only rate limit file with a pointer
    (RULES_D / "11030-rate-limit.conf").write_text(
        "# Rate limits now compiled into 11050-ngfw.conf (real IP counters).\n",
        encoding="utf-8",
    )

    # Lightweight Caddy marker (UAM-style hooks reserved)
    NGFW_CADDY.parent.mkdir(parents=True, exist_ok=True)
    NGFW_CADDY.write_text(
        "# NikTiar NGFW — enforcement is primarily NikTiar WAF (11050-ngfw.conf)\n",
        encoding="utf-8",
    )
    rule_count = sum(1 for ln in lines if ln.startswith("SecRule "))
    return {"ok": True, "rules": rule_count, "next_id": rid}


def new_policy_id() -> str:
    return "pol_" + secrets.token_hex(4)


def new_object_id(prefix: str = "obj") -> str:
    return f"{prefix}_" + secrets.token_hex(3)
