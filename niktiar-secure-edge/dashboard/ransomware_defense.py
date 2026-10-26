"""NikTiar™ Ransomware Defense — layered edge controls (DNS + WAF + URL + hardening).

Honest scope:
  Secure Edge reduces web-borne delivery and C2/leak-site reachability through this
  appliance. It does NOT replace endpoint EDR and does NOT guarantee zero ransomware.
"""
from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

RUNTIME = Path(os.getenv("RUNTIME_DIR") or "/runtime")
RULES_D = RUNTIME / "coraza-rules.d"
POLICY_PATH = RUNTIME / "ransomware_defense.json"

DEFAULT_POLICY: Dict[str, Any] = {
    "enabled": True,
    "mode": "block",  # block | log
    "dns_category": True,  # enforce ransomware DNS category (via dns_filter policy)
    "block_ransom_note_paths": True,
    "block_double_extension_downloads": True,
    "block_script_droppers": True,
    "block_archive_droppers": True,
    "block_webdav_write": True,
    "block_tor2web_gateways": True,
    "block_suspicious_exfil_paths": True,
    "sellable_claims": [
        "Sinkholes known ransomware leak-site / panel / C2 domains (DNS Filter)",
        "Blocks ransom-note and staging URL patterns on the web edge (WAF)",
        "Blocks common dropper download extensions and WebDAV write abuse",
        "Complements endpoint EDR — does not replace host encryption protection",
    ],
    "never_claim": [
        "100% ransomware prevention",
        "Stops all endpoint file encryption",
        "Zero ransomware SLA / guarantee",
    ],
}

# WAF path / filename patterns associated with ransomware staging and notes
RANSOM_NOTE_RX = (
    r"(?i)/(?:README|HOW_TO|DECRYPT|RESTORE|RECOVERY|UNLOCK)[^/]*"
    r"(?:DECRYPT|RANSOM|LOCKBIT|CONTI|BLACKCAT|ALPHV|PLAY|QILIN|RHYSIDA|AKIRA)"
)
RANSOM_NOTE_FILES_RX = (
    r"(?i)/(?:README_FOR_DECRYPT|HOW_TO_DECRYPT|DECRYPT_INSTRUCTIONS|"
    r"RECOVERY_FILES|!!!READ_ME!!!|_readme_|\.html\.hta)(?:$|\?|/)"
)
DOUBLE_EXT_RX = (
    r"(?i)\.(?:pdf|doc|docx|xls|xlsx|jpg|png|txt)\.(?:exe|scr|js|vbs|bat|cmd|ps1|msi)(?:$|\?)"
)
SCRIPT_DROPPER_RX = (
    r"(?i)\.(?:ps1|vbs|js|jse|wsf|hta|bat|cmd|msi)(?:$|\?)"
)
ARCHIVE_DROPPER_RX = (
    r"(?i)\.(?:iso|img|vhd|vhdx|lnk)(?:$|\?)"
)
TOR2WEB_RX = (
    r"(?i)(?:\.onion\.(?:to|link|city|cab|direct|ly|ws)|onion\.to/|tor2web)"
)
EXFIL_PATH_RX = (
    r"(?i)/(?:steal|exfil|loot|dump(?:er)?|wallet(?:s)?|seed(?:phrase)?|bitcoin|monero)(?:/|$|\?)"
)


def default_policy() -> Dict[str, Any]:
    return deepcopy(DEFAULT_POLICY)


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
    base.update({k: v for k, v in data.items() if k in base or k in ("updated_at", "notes")})
    return base


def save_policy(pol: Dict[str, Any]) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    pol = dict(pol)
    pol["updated_at"] = int(time.time())
    # Keep claim lists authoritative from code (do not let operators rewrite claims via API)
    pol["sellable_claims"] = list(DEFAULT_POLICY["sellable_claims"])
    pol["never_claim"] = list(DEFAULT_POLICY["never_claim"])
    POLICY_PATH.write_text(json.dumps(pol, indent=2), encoding="utf-8")


def catalog() -> Dict[str, Any]:
    return {
        "name": "NikTiar Ransomware Defense",
        "layers": [
            {
                "id": "dns",
                "label": "DNS Filter — ransomware category",
                "hint": "Sinkholes leak sites, panels, and known C2 domains from curated + live feeds.",
            },
            {
                "id": "waf_notes",
                "label": "WAF — ransom note / staging paths",
                "hint": "Blocks URI patterns used for decrypt instructions and staging pages.",
            },
            {
                "id": "waf_droppers",
                "label": "WAF — dropper downloads",
                "hint": "Blocks double-extension and high-risk script/ISO download paths.",
            },
            {
                "id": "waf_webdav",
                "label": "WAF — WebDAV write abuse",
                "hint": "Blocks PROPFIND/MKCOL/PUT used to plant payloads on exposed shares.",
            },
            {
                "id": "url_filter",
                "label": "URL Filter — ransomware category",
                "hint": "Path keywords tied to ransomware tooling on HTTP requests.",
            },
        ],
        # Operator-facing only: capability summary (no sales/SLA meta wording).
        "summary": (
            "Layered DNS and web controls that reduce ransomware exposure on this edge. "
            "Use alongside endpoint security and backups."
        ),
    }


def write_waf_rules(pol: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    pol = pol or load_policy()
    RULES_D.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Generated by NikTiar Ransomware Defense",
        f"# enabled={pol.get('enabled')} mode={pol.get('mode')}",
    ]
    rid = 1107000
    count = 0
    if not pol.get("enabled", True):
        path = RULES_D / "11070-ransomware-defense.conf"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"ok": True, "rules": 0, "path": str(path)}

    mode = (pol.get("mode") or "block").lower()
    act = "pass,log" if mode == "log" else "deny,status:403"

    def add(rx: str, msg: str) -> None:
        nonlocal rid, count
        lines.append(
            f'SecRule REQUEST_URI "@rx {rx}" '
            f'"id:{rid},phase:1,{act},log,msg:\'NikTiar Ransomware Defense: {msg}\'"'
        )
        rid += 1
        count += 1

    if pol.get("block_ransom_note_paths", True):
        add(RANSOM_NOTE_RX, "ransom note path")
        add(RANSOM_NOTE_FILES_RX, "ransom note file")
    if pol.get("block_double_extension_downloads", True):
        add(DOUBLE_EXT_RX, "double-extension dropper")
    if pol.get("block_script_droppers", True):
        # Only block scripts when Content-Disposition/download-ish URI OR explicit download path
        lines.append(
            f'SecRule REQUEST_URI "@rx (?i)/(?:download|dl|files|payload|update|install)/" '
            f'"id:{rid},phase:1,{act},log,chain,msg:\'NikTiar Ransomware Defense: script dropper path\'"'
        )
        rid += 1
        lines.append(f'SecRule REQUEST_URI "@rx {SCRIPT_DROPPER_RX}"')
        rid += 1
        count += 1
    if pol.get("block_archive_droppers", True):
        lines.append(
            f'SecRule REQUEST_URI "@rx (?i)/(?:download|dl|files|payload|update|install)/" '
            f'"id:{rid},phase:1,{act},log,chain,msg:\'NikTiar Ransomware Defense: ISO/IMG dropper\'"'
        )
        rid += 1
        lines.append(f'SecRule REQUEST_URI "@rx {ARCHIVE_DROPPER_RX}"')
        rid += 1
        count += 1
    if pol.get("block_tor2web_gateways", True):
        add(TOR2WEB_RX, "Tor2web / onion gateway")
    if pol.get("block_suspicious_exfil_paths", True):
        add(EXFIL_PATH_RX, "suspicious exfil path")

    if pol.get("block_webdav_write", True):
        lines.append(
            'SecRule REQUEST_METHOD "@rx ^(?:PUT|MKCOL|MOVE|COPY|PROPPATCH)$" '
            f'"id:{rid},phase:1,{act},log,msg:\'NikTiar Ransomware Defense: WebDAV write method\'"'
        )
        rid += 1
        count += 1
        lines.append(
            'SecRule REQUEST_METHOD "@streq PROPFIND" '
            f'"id:{rid},phase:1,{act},log,msg:\'NikTiar Ransomware Defense: WebDAV PROPFIND\'"'
        )
        rid += 1
        count += 1

    path = RULES_D / "11070-ransomware-defense.conf"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "rules": count, "path": str(path)}


def ensure_dns_ransomware_category() -> Dict[str, Any]:
    """Ensure DNS Filter policy enforces the ransomware category when defense pack is on."""
    try:
        from dns_filter import load_policy as load_dns, save_policy as save_dns

        dns = load_dns()
        cats = list(dns.get("enabled_categories") or [])
        if "ransomware" not in cats:
            cats.append("ransomware")
            dns["enabled_categories"] = cats
            dns["enabled"] = True
            save_dns(dns)
            return {"ok": True, "enabled_categories": cats, "updated": True}
        return {"ok": True, "enabled_categories": cats, "updated": False}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def ensure_url_filter_ransomware(cfg: Dict[str, Any]) -> None:
    ngfw = (cfg.setdefault("global", {})).setdefault("ngfw", {})
    uf = ngfw.setdefault("url_filter", {})
    cats = list(uf.get("categories") or [])
    if "ransomware" not in cats:
        cats.append("ransomware")
        uf["categories"] = cats
    uf.setdefault("enabled", True)


def apply_ransomware_defense(
    cfg: Optional[Dict[str, Any]] = None, pol: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    pol = pol or load_policy()
    save_policy(pol)
    waf = write_waf_rules(pol)
    dns_meta: Dict[str, Any] = {}
    if pol.get("enabled", True) and pol.get("dns_category", True):
        dns_meta = ensure_dns_ransomware_category()
    if cfg is not None and pol.get("enabled", True):
        ensure_url_filter_ransomware(cfg)
        cfg.setdefault("global", {})["ransomware_defense"] = {
            "enabled": pol.get("enabled"),
            "mode": pol.get("mode"),
            "updated_at": pol.get("updated_at"),
        }
    return {"ok": True, "policy": pol, "waf": waf, "dns": dns_meta, "catalog": catalog()}


def merge_ransomware(cfg: Dict[str, Any]) -> Dict[str, Any]:
    g = cfg.setdefault("global", {})
    snap = g.get("ransomware_defense")
    if not isinstance(snap, dict):
        g["ransomware_defense"] = {
            "enabled": True,
            "mode": "block",
        }
    return cfg
