"""Next-gen enterprise Secure Edge controls — API Shield, Page Shield, Waiting Room,
GraphQL guards, virtual patching, sensitive-data egress, auth hardening, Logpush hooks.
Designed to compete with Cloudflare Advantage-class application security.
"""
from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

_RUNTIME = Path(os.getenv("RUNTIME_DIR") or "/runtime")
RULES_D = _RUNTIME / "coraza-rules.d"
ENTERPRISE_CADDY = _RUNTIME / "enterprise.caddy"

DEFAULT_ENTERPRISE = {
    "api_shield": {
        "enabled": True,
        "require_json_on_api": True,
        "block_debug_methods": True,
        "block_unexpected_content_types": True,
        "max_body_kb": 1024,
    },
    "graphql_guard": {
        "enabled": True,
        "max_depth": 10,
        "block_batch_arrays": True,
        "max_aliases": 15,
    },
    "page_shield": {
        "enabled": True,
        "csp": "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'",
        "referrer_policy": "strict-origin-when-cross-origin",
        "permissions_policy": "geolocation=(), microphone=(), camera=()",
    },
    "waiting_room": {
        "enabled": False,
        "queue_threshold_rps": 50,
        "html_title": "NikTiar Waiting Room",
    },
    "virtual_patching": {
        "enabled": True,
        "block_env_and_secrets": True,
        "block_admin_scanners": True,
        "block_spring_actuator": True,
        "block_wordpress_noise": True,
    },
    "auth_hardening": {
        "enabled": True,
        "paths_regex": r"(?i)^/(login|signin|auth|oauth|token|wp-login\.php|api/.*/(login|token|auth))",
        "max_requests_per_minute": 20,
    },
    "sensitive_data_egress": {
        "enabled": True,
        "block_pan": True,
        "block_ssn": True,
        "mode": "log",
    },
    "honeypot": {
        "enabled": True,
        "paths": ["/.git/config", "/actuator/env", "/server-status", "/phpmyadmin", "/admin.php"],
    },
    "mtls": {
        "enabled": False,
        "mode": "request",
    },
    "leaked_credentials": {
        "enabled": True,
        "mode": "log",
        "note": "Edge flags password fields; full HIBP k-anonymity via /api/enterprise/hibp-check",
    },
    "logpush": {
        "enabled": False,
        "webhook_url": "",
        "include_waf_blocks_only": True,
    },
    "advanced_bot": {
        "enabled": True,
        "pow_challenge": True,
        "block_headless_ua": True,
    },
}


def merge_enterprise(cfg: Dict[str, Any]) -> Dict[str, Any]:
    g = cfg.setdefault("global", {})
    ent = g.setdefault("enterprise", {})
    base = deepcopy(DEFAULT_ENTERPRISE)
    for k, v in base.items():
        if k not in ent:
            ent[k] = deepcopy(v)
        elif isinstance(v, dict):
            for sk, sv in v.items():
                ent[k].setdefault(sk, sv)
    return cfg


def write_enterprise_rules(cfg: Dict[str, Any]) -> None:
    """Write Coraza-safe SecRules (no TX/IP collections — Coraza CRS image rejects them)."""
    RULES_D.mkdir(parents=True, exist_ok=True)
    g = cfg.get("global") or {}
    ent = g.get("enterprise") or DEFAULT_ENTERPRISE
    lines: List[str] = ["# NikTiar Enterprise next-gen rules (1104xxx-1108xxx) — Coraza-safe"]

    vp = ent.get("virtual_patching") or {}
    if vp.get("enabled", True):
        rid = 1104000
        patterns = []
        if vp.get("block_env_and_secrets", True):
            patterns += [
                (r"(?i)(/\.env|/credentials\.json|/id_rsa|/aws/credentials)", "secrets path"),
                (r"(?i)(\.git/HEAD|\.svn/entries|\.DS_Store)", "scm exposure"),
            ]
        if vp.get("block_spring_actuator", True):
            patterns.append((r"(?i)/actuator/(env|heapdump|jolokia|gateway)", "spring actuator"))
        if vp.get("block_admin_scanners", True):
            patterns += [
                (r"(?i)/(phpmyadmin|pma|adminer|manager/html)", "admin scanner"),
                (r"(?i)/(wp-config\.php|xmlrpc\.php)", "wordpress probe"),
            ]
        if vp.get("block_wordpress_noise", True):
            patterns.append((r"(?i)/wp-content/uploads/.*\.(php|phtml|phar)$", "php in uploads"))
        for rx, msg in patterns:
            lines.append(
                f'SecRule REQUEST_URI "@rx {rx}" '
                f'"id:{rid},phase:1,deny,status:403,log,msg:\'NikTiar vpatch: {msg}\'"'
            )
            rid += 1

    api = ent.get("api_shield") or {}
    if api.get("enabled", True):
        rid = 1104100
        if api.get("block_debug_methods", True):
            lines.append(
                f'SecRule REQUEST_METHOD "@rx ^(?:TRACE|TRACK|DEBUG)$" '
                f'"id:{rid},phase:1,deny,status:405,log,msg:\'NikTiar API Shield: debug method\'"'
            )
            rid += 1
        if api.get("require_json_on_api", True):
            # Single-rule heuristic: POST/PUT/PATCH to /api without json content-type
            lines.append(
                f'SecRule REQUEST_URI "@rx (?i)^/api/" '
                f'"id:{rid},phase:2,deny,status:415,log,chain,'
                f'msg:\'NikTiar API Shield: JSON required on /api\'"'
            )
            lines.append('SecRule REQUEST_METHOD "@rx ^(?:POST|PUT|PATCH)$" "chain"')
            lines.append('SecRule REQUEST_HEADERS:Content-Type "!@rx (?i)application/json"')
            rid += 1
        max_kb = int(api.get("max_body_kb") or 1024)
        lines.append(
            f'SecRule REQUEST_HEADERS:Content-Length "@gt {max_kb * 1024}" '
            f'"id:{rid},phase:1,deny,status:413,log,msg:\'NikTiar API Shield: body too large\'"'
        )

    gql = ent.get("graphql_guard") or {}
    if gql.get("enabled", True):
        rid = 1104200
        if gql.get("block_batch_arrays", True):
            lines.append(
                f'SecRule REQUEST_URI "@rx (?i)/graphql" '
                f'"id:{rid},phase:2,deny,status:400,log,chain,'
                f'msg:\'NikTiar GraphQL: batch array blocked\'"'
            )
            lines.append(r'SecRule REQUEST_BODY "@rx ^\s*\["')
            rid += 1
        # Depth / alias: body heuristics on /graphql (escaped braces for SecLang)
        lines.append(
            f'SecRule REQUEST_URI "@rx (?i)/graphql" '
            f'"id:{rid},phase:2,deny,status:400,log,chain,'
            f'msg:\'NikTiar GraphQL: query too deep\'"'
        )
        lines.append('SecRule REQUEST_BODY "@rx ' + (r"\{" * 10) + '"')
        rid += 1
        lines.append(
            f'SecRule REQUEST_URI "@rx (?i)/graphql" '
            f'"id:{rid},phase:2,deny,status:400,log,chain,'
            f'msg:\'NikTiar GraphQL: alias abuse\'"'
        )
        lines.append(r'SecRule REQUEST_BODY "@rx (?i)(__typename.*){8,}"')

    auth = ent.get("auth_hardening") or {}
    if auth.get("enabled", True):
        # Flag auth paths (rate limit via zone rules / CrowdSec). No IP collections.
        rid = 1104300
        path_re = auth.get("paths_regex") or r"(?i)^/(login|signin|auth)"
        lines.append(
            f'SecRule REQUEST_URI "@rx {path_re}" '
            f'"id:{rid},phase:1,pass,log,msg:\'NikTiar auth hardening: auth path seen\'"'
        )

    bot = ent.get("advanced_bot") or {}
    if bot.get("enabled", True) and bot.get("block_headless_ua", True):
        rid = 1104400
        lines.append(
            "SecRule REQUEST_HEADERS:User-Agent "
            '"@rx (?i)(headlesschrome|phantomjs|selenium|playwright|puppeteer|slimerjs|htmlunit)" '
            f'"id:{rid},phase:1,deny,status:403,log,msg:\'NikTiar advanced bot: automation UA\'"'
        )

    sde = ent.get("sensitive_data_egress") or {}
    if sde.get("enabled", True):
        rid = 1104500
        mode = (sde.get("mode") or "log").lower()
        act = "deny,status:500" if mode == "block" else "pass,log"
        # Avoid lookbehind (Coraza RE2/PCRE subset); coarse digit runs only.
        if sde.get("block_pan", True):
            lines.append(
                f'SecRule RESPONSE_BODY "@rx (?:\\d[ -]?){{15,19}}" '
                f'"id:{rid},phase:4,{act},msg:\'NikTiar DLP: possible PAN in response\'"'
            )
            rid += 1
        if sde.get("block_ssn", True):
            lines.append(
                f'SecRule RESPONSE_BODY "@rx \\d{{3}}-\\d{{2}}-\\d{{4}}" '
                f'"id:{rid},phase:4,{act},msg:\'NikTiar DLP: possible SSN in response\'"'
            )

    (RULES_D / "11040-enterprise.conf").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_enterprise_caddy(cfg: Dict[str, Any]) -> None:
    g = cfg.get("global") or {}
    ent = g.get("enterprise") or DEFAULT_ENTERPRISE
    lines = ["# NikTiar Enterprise edge behaviors"]

    hp = ent.get("honeypot") or {}
    if hp.get("enabled", True):
        paths = hp.get("paths") or []
        for i, p in enumerate(paths):
            p = str(p).strip()
            if not p:
                continue
            m = f"hp_{i}"
            lines.append(f"@{m} path {p}")
            lines.append(f"handle @{m} {{")
            lines.append('\theader X-NikTiar-Honeypot "1"')
            lines.append('\trespond "Not Found" 404')
            lines.append("}")

    wr = ent.get("waiting_room") or {}
    if wr.get("enabled"):
        title = (wr.get("html_title") or "Waiting Room").replace("`", "").replace('"', "")
        lines.append("handle /cdn-cgi/waiting-room/pass {")
        lines.append('\theader Set-Cookie "niktiar_wr=1; Path=/; Max-Age=120; HttpOnly; SameSite=Lax"')
        lines.append('\theader Location "/"')
        lines.append("\trespond 302")
        lines.append("}")
        lines.append("@wr_need {")
        lines.append("\tnot header Cookie *niktiar_wr=1*")
        lines.append("\tnot path /cdn-cgi/*")
        lines.append("\tnot path /healthz")
        lines.append("\tnot path /edge-info")
        lines.append("}")
        lines.append("handle @wr_need {")
        lines.append("\theader Content-Type text/html")
        lines.append(
            f'\trespond `<!doctype html><html><head><title>{title}</title></head>'
            "<body style='font-family:system-ui;background:#0b1220;color:#e8eef7;"
            "display:flex;align-items:center;justify-content:center;height:100vh;margin:0'>"
            f"<div style='text-align:center;max-width:32rem'><h1>{title}</h1>"
            "<p>You are in a virtual queue while we protect origin capacity.</p>"
            "<p><a style='color:#3d9cf0' href='/cdn-cgi/waiting-room/pass'>Enter site</a></p>"
            "<script>setTimeout(()=>location.href='/cdn-cgi/waiting-room/pass',2500)</script>"
            "</div></body></html>` 429"
        )
        lines.append("}")

    ps = ent.get("page_shield") or {}
    if ps.get("enabled", True):
        csp = (ps.get("csp") or "").replace('"', '\\"')
        lines.append("header {")
        if csp:
            lines.append(f'\tContent-Security-Policy "{csp}"')
        lines.append(f'\tReferrer-Policy "{ps.get("referrer_policy") or "strict-origin-when-cross-origin"}"')
        lines.append(
            f'\tPermissions-Policy "{ps.get("permissions_policy") or "geolocation=(), microphone=(), camera=()"}"'
        )
        lines.append('\tX-NikTiar-Page-Shield "1"')
        lines.append("}")

    ab = ent.get("advanced_bot") or {}
    if ab.get("enabled", True) and ab.get("pow_challenge", True):
        lines.append("handle /cdn-cgi/challenge-platform/pow {")
        lines.append("\theader Content-Type text/html")
        lines.append(
            '\trespond `<!doctype html><html><body style="font-family:system-ui;background:#0b1220;color:#fff;'
            'text-align:center;padding:3rem"><h2>NikTiar Proof-of-Work</h2>'
            "<p id=s>Computing challenge…</p><script>"
            "async function pow(){const t=Date.now().toString(16);let n=0,h='';"
            "while(!h.startsWith('0000')){n++;h=await crypto.subtle.digest('SHA-256',"
            "new TextEncoder().encode(t+':'+n)).then(b=>[...new Uint8Array(b)].map("
            "x=>x.toString(16).padStart(2,'0')).join(''));}"
            "document.cookie='niktiar_uam=1;path=/;max-age=1800';location.href='/';}"
            "pow();</script></body></html>` 200"
        )
        lines.append("}")

    # Auth path marker (do not use handle — would swallow reverse_proxy)
    auth = ent.get("auth_hardening") or {}
    if auth.get("enabled", True):
        rpm = int(auth.get("max_requests_per_minute") or 20)
        lines.append(r"@auth_paths path_regexp (?i)^/(login|signin|auth|oauth|token|wp-login\.php)")
        lines.append(f'header @auth_paths X-NikTiar-Auth-Guard "rpm={rpm}"')

    ENTERPRISE_CADDY.write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_enterprise(cfg: Dict[str, Any]) -> None:
    merge_enterprise(cfg)
    write_enterprise_rules(cfg)
    write_enterprise_caddy(cfg)
