"""
NikTiar™ Security Profiles — Palo Alto–style NGFW profile pack for Secure Edge.

Inspired by industry NGFW practice (Palo Alto Threat Prevention / File Blocking /
Anti-Spyware / URL Filtering / DNS Security / External Dynamic Lists), implemented
with NikTiar WAF + DNS Filter on the dedicated Secure Edge.

This is NOT a re-skin of Palo Alto software and does not claim WildFire/Cortex parity.
See docs/KB117_SECURE_EDGE_NGFW_PARITY_MAP.md for honest capability mapping.
"""
from __future__ import annotations

import json
import os
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

RUNTIME = Path(os.getenv("RUNTIME_DIR") or "/runtime")
RULES_D = RUNTIME / "coraza-rules.d"
EDL_DIR = RUNTIME / "edl"
POLICY_PATH = RUNTIME / "security_profiles.json"

# --- File Blocking (≈ Palo Alto File Blocking profile) ---
# PE + script + shortcut + disk-image droppers commonly used in ransomware delivery
FILE_BLOCK_EXTENSIONS = [
    "exe", "dll", "scr", "msi", "msp", "com", "pif", "cpl", "sys", "drv", "ocx",
    "bat", "cmd", "ps1", "vbs", "vbe", "js", "jse", "wsf", "wsh", "hta", "hlp",
    "lnk", "chm", "iso", "img", "vhd", "vhdx", "dmg",
]
# Office macros / risky docs often used as loaders (block download path or always)
OFFICE_RISKY = ["docm", "xlsm", "pptm", "dotm", "xltm", "ppam"]

# --- Anti-Spyware / C2 path heuristics (HTTP edge) ---
C2_PATH_RX = (
    r"(?i)/(?:gate|panel|botnet|c2|command|beacon|checkin|heartbeat|"
    r"tor2web|onion)|(?:[?&](?:key|token|botid|hwid)+=)"
)

# --- DGA-ish Host heuristic (RE2-safe — no lookaheads) ---
# Long leftmost label with mixed letters+digits, typical of DGA / staging hosts.
DGA_HOST_RX = (
    r"(?i)^[a-z0-9]{16,}[0-9][a-z0-9]{0,40}\.[a-z0-9.-]{2,80}\.[a-z]{2,24}$"
)

# --- DNS tunneling style: very long leftmost label ---
DNS_TUNNEL_HOST_RX = r"(?i)^[a-z0-9_-]{40,}\."

DEFAULT_PROFILES: Dict[str, Any] = {
    "preset": "strict_ransomware",  # recommended | strict_ransomware | custom
    "enabled": True,
    # Antivirus / File Blocking
    "file_blocking": {
        "enabled": True,
        "mode": "block",  # block | log
        "block_pe_and_scripts": True,
        "block_office_macros": True,
        "block_disk_images": True,
        "block_pe_magic_upload": True,  # REQUEST_BODY starts with MZ
        "block_unknown_url_downloads": True,  # PE under /download|/files|/payload
    },
    # Anti-Spyware (HTTP + DNS category enforcement)
    "anti_spyware": {
        "enabled": True,
        "mode": "block",
        "dns_sinkhole_categories": [
            "malware",
            "phishing",
            "ransomware",
            "cryptomining",
            "proxy_vpn",
            "newly_registered",
        ],
        "block_c2_paths": True,
        "block_dga_hosts": True,
        "block_dns_tunnel_hosts": True,
    },
    # URL Filtering (category preset)
    "url_filtering": {
        "enabled": True,
        "mode": "block",
        "categories": [
            "malware",
            "phishing",
            "scanning",
            "crypto_mining",
            "ransomware",
            "proxy_avoidance",
            "dynamic_dns",
            "parked",
        ],
    },
    # Vulnerability Protection → keep NikTiar WAF on + virtual patching
    "vulnerability_protection": {
        "enabled": True,
        "ensure_waf_on": True,
        "ensure_virtual_patching": True,
        "min_security_level": "medium",
    },
    # External Dynamic Lists (operator + feed-synced files)
    "edl": {
        "enabled": True,
        "block_ip_list": True,
        "block_domain_list": True,
        "block_url_list": True,
    },
    # Optional cloud sandbox / commercial WildFire-class hook
    "sandbox": {
        "enabled": False,
        "webhook_url_env": "NIKTIAR_SANDBOX_WEBHOOK_URL",
        "note": "Optional commercial file/URL analysis webhook — not required for Strict preset.",
    },
}

PRESET_HELP = {
    "recommended": "Balanced — file block risky types on download paths, DNS sinkhole critical cats.",
    "strict_ransomware": (
        "Palo-style ransomware hardening — aggressive file blocking, anti-spyware DNS+DGA, "
        "URL malware/phish/proxy/DDNS, WAF virtual patching. Pair with endpoint EDR."
    ),
    "custom": "Operator-tuned toggles below.",
}


def default_policy() -> Dict[str, Any]:
    return deepcopy(DEFAULT_PROFILES)


def load_policy() -> Dict[str, Any]:
    if not POLICY_PATH.exists():
        pol = default_policy()
        save_policy(pol)
        return pol
    try:
        data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = {}
    base = default_policy()
    for k, v in data.items():
        if k in ("file_blocking", "anti_spyware", "url_filtering", "vulnerability_protection", "edl", "sandbox"):
            if isinstance(v, dict):
                base[k] = {**base.get(k, {}), **v}
        elif k in base or k in ("updated_at", "notes", "preset"):
            base[k] = v
    return base


def save_policy(pol: Dict[str, Any]) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    pol = dict(pol)
    pol["updated_at"] = int(time.time())
    POLICY_PATH.write_text(json.dumps(pol, indent=2), encoding="utf-8")


def apply_preset(name: str) -> Dict[str, Any]:
    pol = default_policy()
    name = (name or "strict_ransomware").lower()
    pol["preset"] = name
    if name == "recommended":
        pol["file_blocking"]["block_pe_and_scripts"] = True
        pol["file_blocking"]["block_office_macros"] = False
        pol["file_blocking"]["block_disk_images"] = True
        pol["anti_spyware"]["block_dga_hosts"] = False
        pol["url_filtering"]["categories"] = [
            "malware",
            "phishing",
            "scanning",
            "ransomware",
            "crypto_mining",
        ]
    elif name == "strict_ransomware":
        pol = default_policy()
        pol["preset"] = "strict_ransomware"
    # custom = leave as loaded/default toggles
    save_policy(pol)
    return pol


def catalog() -> Dict[str, Any]:
    return {
        "name": "NikTiar Security Profiles",
        "inspired_by": [
            "NGFW File Blocking",
            "Anti-Spyware + DNS sinkhole",
            "URL Filtering categories",
            "Vulnerability Protection (WAF)",
            "External Dynamic Lists (EDL)",
            "Optional cloud sandbox hook",
        ],
        "presets": [
            {"id": k, "hint": v} for k, v in PRESET_HELP.items()
        ],
        "summary": (
            "Security Profiles group File Blocking, Anti-Spyware, URL Filtering, "
            "Vulnerability Protection, and threat lists for this dedicated edge."
        ),
    }


def _ext_rx(exts: List[str]) -> str:
    return r"(?i)\.(?:" + "|".join(re.escape(e) for e in exts) + r")(?:$|\?)"


def write_file_blocking(pol: Dict[str, Any], lines: List[str], rid: int) -> int:
    fb = pol.get("file_blocking") or {}
    if not fb.get("enabled", True):
        return rid
    mode = (fb.get("mode") or "block").lower()
    act = "pass,log" if mode == "log" else "deny,status:403"
    exts: List[str] = []
    if fb.get("block_pe_and_scripts", True):
        exts.extend(FILE_BLOCK_EXTENSIONS)
    if fb.get("block_office_macros", True):
        exts.extend(OFFICE_RISKY)
    if fb.get("block_disk_images", True):
        for e in ("iso", "img", "vhd", "vhdx", "dmg"):
            if e not in exts:
                exts.append(e)
    if exts:
        rx = _ext_rx(sorted(set(exts)))
        if fb.get("block_unknown_url_downloads", True):
            lines.append(
                f'SecRule REQUEST_URI "@rx (?i)/(?:download|dl|files|payload|update|install|uploads?)/" '
                f'"id:{rid},phase:1,{act},log,chain,msg:\'NikTiar File Blocking download path\'"'
            )
            rid += 1
            lines.append(f'SecRule REQUEST_URI "@rx {rx}"')
            rid += 1
        # Always block PE/scripts on any path when strict
        if (pol.get("preset") or "") == "strict_ransomware":
            lines.append(
                f'SecRule REQUEST_URI "@rx {rx}" '
                f'"id:{rid},phase:1,{act},log,msg:\'NikTiar File Blocking extension\'"'
            )
            rid += 1
    if fb.get("block_pe_magic_upload", True):
        # PE magic in body (uploads) — phase 2
        lines.append(
            f'SecRule REQUEST_BODY "@rx ^MZ" '
            f'"id:{rid},phase:2,{act},log,msg:\'NikTiar File Blocking PE upload (MZ)\'"'
        )
        rid += 1
        lines.append(
            f'SecRule REQUEST_HEADERS:Content-Type "@rx (?i)application/(?:x-msdownload|x-msdos-program|octet-stream)" '
            f'"id:{rid},phase:1,{act},log,chain,msg:\'NikTiar File Blocking PE content-type\'"'
        )
        rid += 1
        lines.append(f'SecRule REQUEST_URI "@rx {_ext_rx(["exe", "dll", "scr", "msi"])}"')
        rid += 1
    return rid


def write_anti_spyware(pol: Dict[str, Any], lines: List[str], rid: int) -> int:
    asp = pol.get("anti_spyware") or {}
    if not asp.get("enabled", True):
        return rid
    mode = (asp.get("mode") or "block").lower()
    act = "pass,log" if mode == "log" else "deny,status:403"
    if asp.get("block_c2_paths", True):
        lines.append(
            f'SecRule REQUEST_URI "@rx {C2_PATH_RX}" '
            f'"id:{rid},phase:1,{act},log,msg:\'NikTiar Anti-Spyware C2 path\'"'
        )
        rid += 1
    if asp.get("block_dga_hosts", True):
        lines.append(
            f'SecRule REQUEST_HEADERS:Host "@rx {DGA_HOST_RX}" '
            f'"id:{rid},phase:1,{act},log,msg:\'NikTiar Anti-Spyware DGA-like Host\'"'
        )
        rid += 1
    if asp.get("block_dns_tunnel_hosts", True):
        lines.append(
            f'SecRule REQUEST_HEADERS:Host "@rx {DNS_TUNNEL_HOST_RX}" '
            f'"id:{rid},phase:1,{act},log,msg:\'NikTiar Anti-Spyware DNS-tunnel Host\'"'
        )
        rid += 1
    return rid


def write_edl_rules(pol: Dict[str, Any], lines: List[str], rid: int) -> int:
    edl = pol.get("edl") or {}
    if not edl.get("enabled", True):
        return rid
    EDL_DIR.mkdir(parents=True, exist_ok=True)
    mode = "deny,status:403"
    # Domain EDL
    domain_file = EDL_DIR / "domains.txt"
    if edl.get("block_domain_list", True) and domain_file.exists():
        domains = [
            d.strip().lower()
            for d in domain_file.read_text(encoding="utf-8").splitlines()
            if d.strip() and not d.startswith("#")
        ][:2000]
        chunk = 40
        for i in range(0, len(domains), chunk):
            part = domains[i : i + chunk]
            rx = "(?i)(?:^|\\.)(?:" + "|".join(re.escape(d) for d in part) + ")$"
            lines.append(
                f'SecRule REQUEST_HEADERS:Host "@rx {rx}" '
                f'"id:{rid},phase:1,{mode},log,msg:\'NikTiar EDL domain block\'"'
            )
            rid += 1
    # IP EDL
    ip_file = EDL_DIR / "ips.txt"
    if edl.get("block_ip_list", True) and ip_file.exists():
        ips = [
            x.strip()
            for x in ip_file.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.startswith("#")
        ][:500]
        for ip in ips:
            if not re.match(r"^[\d.:a-fA-F/]+$", ip):
                continue
            lines.append(
                f'SecRule REMOTE_ADDR "@ipMatch {ip}" '
                f'"id:{rid},phase:1,{mode},log,msg:\'NikTiar EDL IP block\'"'
            )
            rid += 1
    # URL path EDL
    url_file = EDL_DIR / "urls.txt"
    if edl.get("block_url_list", True) and url_file.exists():
        paths = [
            x.strip()
            for x in url_file.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.startswith("#")
        ][:500]
        for p in paths:
            esc = p.replace("\\", "\\\\").replace('"', '\\"')
            if p.startswith("@rx "):
                op = p
            else:
                op = f"@contains {esc}"
            lines.append(
                f'SecRule REQUEST_URI "{op}" '
                f'"id:{rid},phase:1,{mode},log,msg:\'NikTiar EDL URL block\'"'
            )
            rid += 1
    return rid


def sync_dns_categories(pol: Dict[str, Any]) -> Dict[str, Any]:
    asp = pol.get("anti_spyware") or {}
    if not asp.get("enabled", True):
        return {"ok": True, "skipped": True}
    cats = list(asp.get("dns_sinkhole_categories") or [])
    try:
        from dns_filter import load_policy, save_policy

        dns = load_policy()
        enabled = set(dns.get("enabled_categories") or [])
        enabled.update(cats)
        dns["enabled_categories"] = sorted(enabled)
        dns["enabled"] = True
        save_policy(dns)
        return {"ok": True, "enabled_categories": dns["enabled_categories"]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def sync_url_filter(cfg: Dict[str, Any], pol: Dict[str, Any]) -> None:
    uf_pol = pol.get("url_filtering") or {}
    if not uf_pol.get("enabled", True):
        return
    ngfw = (cfg.setdefault("global", {})).setdefault("ngfw", {})
    uf = ngfw.setdefault("url_filter", {})
    uf["enabled"] = True
    uf["mode"] = uf_pol.get("mode") or "block"
    # merge categories
    cats = list(uf.get("categories") or [])
    for c in uf_pol.get("categories") or []:
        if c not in cats:
            cats.append(c)
    uf["categories"] = cats


def sync_vulnerability(cfg: Dict[str, Any], pol: Dict[str, Any]) -> None:
    vp = pol.get("vulnerability_protection") or {}
    if not vp.get("enabled", True):
        return
    g = cfg.setdefault("global", {})
    if vp.get("ensure_waf_on", True):
        g["waf_enabled"] = True
    level = g.get("security_level") or "medium"
    order = ["off", "essentially_off", "low", "medium", "high", "under_attack"]
    want = vp.get("min_security_level") or "medium"
    if level in order and want in order and order.index(level) < order.index(want):
        g["security_level"] = want
    if vp.get("ensure_virtual_patching", True):
        ent = g.get("enterprise")
        if not isinstance(ent, dict):
            ent = {}
            g["enterprise"] = ent
        vp_ent = ent.get("virtual_patching")
        if not isinstance(vp_ent, dict):
            vp_ent = {}
            ent["virtual_patching"] = vp_ent
        vp_ent["enabled"] = True


def write_profile_rules(pol: Dict[str, Any]) -> Dict[str, Any]:
    RULES_D.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Generated by NikTiar Security Profiles (NGFW-style)",
        f"# preset={pol.get('preset')} enabled={pol.get('enabled')}",
    ]
    rid = 1108000
    if not pol.get("enabled", True):
        path = RULES_D / "11080-security-profiles.conf"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"ok": True, "rules_start": 1108000, "path": str(path)}
    rid = write_file_blocking(pol, lines, rid)
    rid = write_anti_spyware(pol, lines, rid)
    rid = write_edl_rules(pol, lines, rid)
    path = RULES_D / "11080-security-profiles.conf"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "next_rid": rid, "path": str(path), "lines": len(lines)}


def ensure_edl_templates() -> None:
    EDL_DIR.mkdir(parents=True, exist_ok=True)
    for name, header in (
        ("domains.txt", "# NikTiar EDL domains — one FQDN per line\n"),
        ("ips.txt", "# NikTiar EDL IPs/CIDRs — one per line\n"),
        ("urls.txt", "# NikTiar EDL URL path contains — one per line (or @rx ...)\n"),
    ):
        p = EDL_DIR / name
        if not p.exists():
            p.write_text(header, encoding="utf-8")


def apply_security_profiles(
    cfg: Optional[Dict[str, Any]] = None, pol: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    pol = pol or load_policy()
    # If preset named, re-expand from template first time / when switching
    if pol.get("preset") in ("strict_ransomware", "recommended") and not pol.get("_customized"):
        # keep operator toggles if already saved; only fill missing
        pass
    save_policy(pol)
    ensure_edl_templates()
    rules = write_profile_rules(pol)
    dns = sync_dns_categories(pol)
    if cfg is not None:
        sync_url_filter(cfg, pol)
        sync_vulnerability(cfg, pol)
        cfg.setdefault("global", {})["security_profiles"] = {
            "enabled": pol.get("enabled"),
            "preset": pol.get("preset"),
            "updated_at": pol.get("updated_at"),
        }
    # Keep ransomware defense aligned when Strict preset
    ransom_meta: Dict[str, Any] = {}
    if pol.get("enabled") and pol.get("preset") == "strict_ransomware":
        try:
            from ransomware_defense import apply_ransomware_defense, load_policy as load_rw, save_policy as save_rw

            rw = load_rw()
            rw["enabled"] = True
            rw["mode"] = "block"
            rw["dns_category"] = True
            for k in (
                "block_ransom_note_paths",
                "block_double_extension_downloads",
                "block_script_droppers",
                "block_archive_droppers",
                "block_webdav_write",
                "block_tor2web_gateways",
                "block_suspicious_exfil_paths",
            ):
                rw[k] = True
            save_rw(rw)
            ransom_meta = apply_ransomware_defense(cfg, rw)
        except Exception as exc:  # noqa: BLE001
            ransom_meta = {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "policy": pol,
        "rules": rules,
        "dns": dns,
        "ransomware": ransom_meta,
        "catalog": catalog(),
    }


def merge_security_profiles(cfg: Dict[str, Any]) -> Dict[str, Any]:
    g = cfg.setdefault("global", {})
    if not isinstance(g.get("security_profiles"), dict):
        g["security_profiles"] = {"enabled": True, "preset": "strict_ransomware"}
    return cfg
