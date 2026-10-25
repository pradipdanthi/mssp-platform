"""Strong multi-tenant isolation helpers for NikTiar Secure Edge (shared + dedicated)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_RUNTIME = Path(os.getenv("RUNTIME_DIR") or "/runtime")
TENANT_MAP_PATH = _RUNTIME / "tenant_map.json"
ISOLATION_META_PATH = _RUNTIME / "isolation.json"

MODE = (os.getenv("SECURE_EDGE_MODE") or "shared").lower()
PINNED_TENANT = (os.getenv("NIKTIAR_TENANT_CODE") or "").strip().upper()


def normalize_host(host: Optional[str]) -> str:
    return (host or "").strip().lower().split(":")[0]


def normalize_tenant(code: Optional[str]) -> str:
    return (code or "").strip().upper()


def build_tenant_map(cfg: Dict[str, Any]) -> Dict[str, str]:
    """public_hostname → tenant_short_code."""
    out: Dict[str, str] = {}
    for z in cfg.get("zones") or []:
        host = normalize_host(z.get("public_hostname"))
        tenant = normalize_tenant(z.get("tenant_short_code")) or "UNKNOWN"
        if host:
            out[host] = tenant
    return out


def save_tenant_map(cfg: Dict[str, Any]) -> Dict[str, str]:
    _RUNTIME.mkdir(parents=True, exist_ok=True)
    m = build_tenant_map(cfg)
    TENANT_MAP_PATH.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    meta = {
        "mode": MODE,
        "pinned_tenant": PINNED_TENANT or None,
        "zone_count": len(m),
        "isolation": {
            "unknown_host": "deny_421",
            "firewall": "per_zone_host_scoped",
            "custom_rules": "host_or_tenant_scoped",
            "rate_limit": "host_scoped",
            "events": "hostname_to_tenant_map",
            "default_origin_fallthrough": False,
        },
    }
    ISOLATION_META_PATH.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return m


def load_tenant_map() -> Dict[str, str]:
    if not TENANT_MAP_PATH.exists():
        return {}
    try:
        data = json.loads(TENANT_MAP_PATH.read_text(encoding="utf-8"))
        return {normalize_host(k): normalize_tenant(v) for k, v in (data or {}).items()}
    except Exception:  # noqa: BLE001
        return {}


def tenant_for_host(host: Optional[str], cfg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    h = normalize_host(host)
    if not h:
        return None
    m = build_tenant_map(cfg) if cfg else load_tenant_map()
    return m.get(h)


def enforce_dedicated_zones(cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """In dedicated mode, drop zones that are not the pinned tenant."""
    warnings: List[str] = []
    if MODE != "dedicated" or not PINNED_TENANT:
        return cfg, warnings
    kept = []
    for z in cfg.get("zones") or []:
        t = normalize_tenant(z.get("tenant_short_code"))
        if t and t != PINNED_TENANT:
            warnings.append(
                f"dropped zone {z.get('public_hostname')} tenant={t} (dedicated pin={PINNED_TENANT})"
            )
            continue
        if not t:
            z = dict(z)
            z["tenant_short_code"] = PINNED_TENANT
        kept.append(z)
    cfg["zones"] = kept
    # Drop custom rules for other tenants
    rules = []
    for r in cfg.get("custom_waf_rules") or []:
        rt = normalize_tenant(r.get("tenant_short_code"))
        if rt and rt != PINNED_TENANT:
            warnings.append(f"dropped custom rule {r.get('id')} tenant={rt}")
            continue
        if not rt:
            r = dict(r)
            r["tenant_short_code"] = PINNED_TENANT
        rules.append(r)
    cfg["custom_waf_rules"] = rules
    return cfg, warnings


def zones_for_tenant(cfg: Dict[str, Any], tenant: str) -> List[Dict[str, Any]]:
    t = normalize_tenant(tenant)
    return [z for z in (cfg.get("zones") or []) if normalize_tenant(z.get("tenant_short_code")) == t]


def redact_zone_for_tenant(zone: Dict[str, Any], viewer_tenant: Optional[str], *, mssp_admin: bool) -> Optional[Dict[str, Any]]:
    """Return zone dict visible to viewer; None if cross-tenant leak."""
    if mssp_admin and not viewer_tenant:
        return zone
    zt = normalize_tenant(zone.get("tenant_short_code"))
    vt = normalize_tenant(viewer_tenant)
    if vt and zt and vt != zt:
        return None
    if mssp_admin:
        return zone
    # tenant-scoped viewer: never expose sibling data
    out = dict(zone)
    return out


def filter_config_view(cfg: Dict[str, Any], viewer_tenant: Optional[str], *, mssp_admin: bool) -> Dict[str, Any]:
    """Return a config projection that cannot leak other tenants' zones/rules/origins."""
    from copy import deepcopy

    out = deepcopy(cfg)
    vt = normalize_tenant(viewer_tenant)
    if mssp_admin and not vt:
        return out
    zones = []
    for z in out.get("zones") or []:
        rz = redact_zone_for_tenant(z, vt, mssp_admin=mssp_admin)
        if rz is not None:
            zones.append(rz)
    out["zones"] = zones
    rules = []
    for r in out.get("custom_waf_rules") or []:
        rt = normalize_tenant(r.get("tenant_short_code"))
        rh = normalize_host(r.get("public_hostname"))
        if vt:
            if rt and rt != vt:
                continue
            if rh:
                owner = tenant_for_host(rh, cfg)
                if owner and owner != vt:
                    continue
            if not rt and not rh:
                # unscoped rule on shared = MSSP-only; hide from tenant viewers
                if not mssp_admin:
                    continue
        rules.append(r)
    out["custom_waf_rules"] = rules
    return out


def assert_zone_writable(zone: Dict[str, Any], viewer_tenant: Optional[str], *, mssp_admin: bool) -> None:
    vt = normalize_tenant(viewer_tenant)
    zt = normalize_tenant(zone.get("tenant_short_code"))
    if MODE == "dedicated" and PINNED_TENANT:
        if zt and zt != PINNED_TENANT:
            raise PermissionError(f"dedicated edge pinned to {PINNED_TENANT}")
        return
    if mssp_admin and not vt:
        return
    if not vt:
        raise PermissionError("tenant scope required")
    if zt and zt != vt:
        raise PermissionError("cross-tenant zone mutation denied")


def host_scoped_secrule_prefix(host: str, rid: int, phase: int = 1) -> str:
    """First chain rule locking a SecRule to one Host (strong shared isolation)."""
    h = normalize_host(host).replace("'", "")
    return (
        f'SecRule REQUEST_HEADERS:Host "@streq {h}" '
        f'"id:{rid},phase:{phase},chain,log"'
    )


def validate_custom_rule_scope(rule: Dict[str, Any], *, mssp_admin: bool) -> Dict[str, Any]:
    """Shared mode: custom rules must declare tenant_short_code and/or public_hostname."""
    r = dict(rule)
    if MODE == "dedicated" and PINNED_TENANT:
        r["tenant_short_code"] = normalize_tenant(r.get("tenant_short_code")) or PINNED_TENANT
        return r
    t = normalize_tenant(r.get("tenant_short_code"))
    h = normalize_host(r.get("public_hostname"))
    if not t and not h and not mssp_admin:
        raise ValueError("custom rule requires tenant_short_code or public_hostname")
    if t:
        r["tenant_short_code"] = t
    if h:
        r["public_hostname"] = h
    return r


_SAFE = re.compile(r"[^a-zA-Z0-9_]")


def safe_id(s: str) -> str:
    return _SAFE.sub("_", s)[:48]
