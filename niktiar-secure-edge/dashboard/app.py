"""NikTiar Secure Edge — appliance dashboard (NikTiar WAF / Firewall / NGFW)."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import edge_config as ec

RUNTIME = Path(os.getenv("RUNTIME_DIR") or "/runtime")
CONTROL = (os.getenv("NIKTIAR_CONTROL_URL") or "").rstrip("/")
TOKEN = os.getenv("NIKTIAR_APPLIANCE_TOKEN") or ""
HOST = os.getenv("SECURE_EDGE_HOSTNAME") or "niktiar-secure-edge"
# Product default: dedicated only. Shared multi-tenant is not offered commercially.
_raw_mode = (os.getenv("SECURE_EDGE_MODE") or "dedicated").lower().strip()
if _raw_mode == "shared":
    MODE = "dedicated"
else:
    MODE = _raw_mode if _raw_mode in ("dedicated",) else "dedicated"
FORM_FACTOR = (os.getenv("SECURE_EDGE_FORM_FACTOR") or "ha_pair").lower().strip()
if FORM_FACTOR not in ("ha_pair", "physical"):
    FORM_FACTOR = "ha_pair"
HA_ROLE = (os.getenv("SECURE_EDGE_HA_ROLE") or "primary").lower().strip()
DASH_USER = os.getenv("EDGE_DASHBOARD_USER") or "admin"


def _deployment_label() -> str:
    # Customer-facing: never surface internal form-factor jargon (HA pair / physical) in the header.
    return "Dedicated Edge"
DASH_PASS = os.getenv("EDGE_DASHBOARD_PASSWORD") or "NikTiarEdge!ChangeMe"
ACCESS_LOG = Path(os.getenv("ACCESS_LOG") or "/runtime/niktiar-access.log")
WAF_CONTAINER = os.getenv("WAF_CONTAINER") or "niktiar-se-waf"
CS_CONTAINER = os.getenv("CROWDSEC_CONTAINER") or "niktiar-se-crowdsec"
SESSIONS: Dict[str, float] = {}
SESSION_TTL = 12 * 3600

# Point engine at runtime paths
ec.RUNTIME = RUNTIME
ec.CONFIG_PATH = RUNTIME / "edge_config.json"
ec.OVERRIDES = RUNTIME / "coraza-overrides"
ec.RULES_D = RUNTIME / "coraza-rules.d"
ec.SITES_CADDY = RUNTIME / "sites.caddy"
ec.SITES_TLS = RUNTIME / "sites_tls.caddy"
ec.FIREWALL_CADDY = RUNTIME / "firewall.caddy"
ec.WAF_CONTAINER = WAF_CONTAINER

PINNED_TENANT = (os.getenv("NIKTIAR_TENANT_CODE") or "").strip().upper()

try:
    import enterprise_features as ef

    ef.RULES_D = RUNTIME / "coraza-rules.d"
    ef.ENTERPRISE_CADDY = RUNTIME / "enterprise.caddy"
except Exception:  # noqa: BLE001
    ef = None  # type: ignore

try:
    import tenant_isolation as ti

    ti._RUNTIME = RUNTIME
    ti.TENANT_MAP_PATH = RUNTIME / "tenant_map.json"
    ti.ISOLATION_META_PATH = RUNTIME / "isolation.json"
    ti.MODE = MODE
    ti.PINNED_TENANT = PINNED_TENANT
except Exception:  # noqa: BLE001
    ti = None  # type: ignore

app = FastAPI(title="NikTiar Secure Edge", version="4.1.0")
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(static_dir)), name="assets")

try:
    import ngfw_features as ngfw
except Exception:  # noqa: BLE001
    ngfw = None  # type: ignore

try:
    import dns_filter as dnsf

    dnsf.RUNTIME = RUNTIME
    dnsf.FEEDS_DIR = RUNTIME / "dns-feeds"
    dnsf.FILTER_DIR = RUNTIME / "dns-filter"
    dnsf.POLICY_PATH = RUNTIME / "dns-filter" / "policy.json"
    dnsf.MANIFEST_PATH = RUNTIME / "dns-feeds" / "manifest.json"
    dnsf.WAF_LIST = RUNTIME / "dns-feeds" / "waf_host_blocklist.txt"
    dnsf.RULES_D = RUNTIME / "coraza-rules.d"
except Exception:  # noqa: BLE001
    dnsf = None  # type: ignore

try:
    import ransomware_defense as rwd

    rwd.RUNTIME = RUNTIME
    rwd.RULES_D = RUNTIME / "coraza-rules.d"
    rwd.POLICY_PATH = RUNTIME / "ransomware_defense.json"
except Exception:  # noqa: BLE001
    rwd = None  # type: ignore

try:
    import security_profiles as secprof

    secprof.RUNTIME = RUNTIME
    secprof.RULES_D = RUNTIME / "coraza-rules.d"
    secprof.EDL_DIR = RUNTIME / "edl"
    secprof.POLICY_PATH = RUNTIME / "security_profiles.json"
except Exception:  # noqa: BLE001
    secprof = None  # type: ignore


class LoginIn(BaseModel):
    username: str
    password: str


class GlobalSettingsIn(BaseModel):
    security_level: Optional[str] = None
    waf_enabled: Optional[bool] = None
    bot_fight_mode: Optional[bool] = None
    browser_integrity_check: Optional[bool] = None
    always_use_https: Optional[bool] = None


class ZoneIn(BaseModel):
    public_hostname: str
    origin_url: str
    tenant_short_code: Optional[str] = "LOCAL"
    ssl_mode: str = "flexible"
    security_level: Optional[str] = None
    under_attack_mode: bool = False
    enabled: bool = True
    waf: Optional[Dict[str, Any]] = None
    firewall: Optional[Dict[str, Any]] = None
    rate_limit_rules: Optional[List[Dict[str, Any]]] = None
    cache: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class CustomRuleIn(BaseModel):
    name: str
    expression: str
    action: str = "block"
    description: Optional[str] = None
    enabled: bool = True
    priority: int = 100
    id: Optional[str] = None
    tenant_short_code: Optional[str] = None
    public_hostname: Optional[str] = None


def _auth(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Login required")
    tok = authorization.split(" ", 1)[1].strip()
    exp = SESSIONS.get(tok)
    if not exp or exp < time.time():
        SESSIONS.pop(tok, None)
        raise HTTPException(status_code=401, detail="Session expired")
    return tok


def _docker_ps() -> List[Dict[str, str]]:
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        rows = []
        for line in (r.stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                rows.append({"name": parts[0], "status": parts[1], "image": parts[2]})
        return rows
    except Exception as exc:  # noqa: BLE001
        return [{"name": "error", "status": str(exc), "image": ""}]


def _parse_access_stats(limit: int = 500) -> Dict[str, Any]:
    blocks = 0
    total = 0
    by_status: Dict[str, int] = {}
    recent: List[Dict[str, Any]] = []
    if ACCESS_LOG.is_file() and not ACCESS_LOG.is_symlink():
        try:
            r = subprocess.run(
                ["tail", "-n", str(limit), str(ACCESS_LOG)],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in (r.stdout or "").splitlines():
                try:
                    obj = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                total += 1
                status = int(obj.get("status") or 0)
                by_status[str(status)] = by_status.get(str(status), 0) + 1
                if status == 403:
                    blocks += 1
                req = obj.get("request") or {}
                recent.append(
                    {
                        "ts": obj.get("ts"),
                        "status": status,
                        "method": req.get("method"),
                        "host": req.get("host"),
                        "uri": req.get("uri"),
                        "client_ip": req.get("client_ip") or req.get("remote_ip"),
                    }
                )
        except Exception:  # noqa: BLE001
            pass
    recent.reverse()
    return {
        "total_sampled": total,
        "waf_blocks_403": blocks,
        "by_status": by_status,
        "recent": recent[:100],
    }


def _crowdsec_decisions() -> List[Dict[str, Any]]:
    try:
        r = subprocess.run(
            ["docker", "exec", CS_CONTAINER, "cscli", "decisions", "list", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode != 0:
            return []
        data = json.loads(r.stdout or "[]")
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def _seed_zones_from_legacy() -> None:
    """Import prior sites.json / control-plane sites into edge_config once."""
    cfg = ec.load_config()
    if cfg.get("zones"):
        return
    sites_path = RUNTIME / "sites.json"
    imported = []
    if sites_path.exists():
        try:
            data = json.loads(sites_path.read_text(encoding="utf-8"))
            imported = data.get("sites") or data if isinstance(data, list) else data.get("sites") or []
        except Exception:  # noqa: BLE001
            imported = []
    for s in imported:
        host = (s.get("public_hostname") or "").lower()
        if not host:
            continue
        z = deepcopy(ec.DEFAULT_ZONE)
        z.update(
            {
                "id": ec.new_id(),
                "public_hostname": host,
                "origin_url": s.get("origin_url") or "http://origin:80",
                "tenant_short_code": s.get("tenant_short_code") or "LOCAL",
                "ssl_mode": "flexible" if (s.get("tls_mode") or "") != "acme" else "full",
            }
        )
        cfg["zones"].append(z)
    if cfg["zones"]:
        ec.apply_all(cfg)


@app.on_event("startup")
def _startup() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME / "coraza-overrides").mkdir(parents=True, exist_ok=True)
    (RUNTIME / "coraza-rules.d").mkdir(parents=True, exist_ok=True)
    if not (RUNTIME / "firewall.caddy").exists():
        (RUNTIME / "firewall.caddy").write_text("# init\n", encoding="utf-8")
    if not (RUNTIME / "sites.caddy").exists():
        (RUNTIME / "sites.caddy").write_text("# init\n", encoding="utf-8")
    if not (RUNTIME / "sites_tls.caddy").exists():
        (RUNTIME / "sites_tls.caddy").write_text("# init\n", encoding="utf-8")
    _seed_zones_from_legacy()
    # Ensure config files exist
    ec.load_config()


@app.get("/")
def index():
    p = static_dir / "index.html"
    if not p.exists():
        return JSONResponse({"error": "UI missing"}, status_code=500)
    return FileResponse(p)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "secure-edge-dashboard", "version": "4.1.0", "hostname": HOST}


@app.post("/api/login")
def login(body: LoginIn):
    if body.username != DASH_USER or body.password != DASH_PASS:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    tok = secrets.token_urlsafe(32)
    SESSIONS[tok] = time.time() + SESSION_TTL
    return {"token": tok, "expires_in": SESSION_TTL, "user": DASH_USER}


@app.get("/api/overview")
def overview(_: str = Depends(_auth)):
    cfg = ec.load_config()
    stats = _parse_access_stats()
    decisions = _crowdsec_decisions()
    rw_pol = None
    if rwd:
        rw_pol = dict(rwd.load_policy())
        rw_pol.pop("sellable_claims", None)
        rw_pol.pop("never_claim", None)
    return {
        "hostname": HOST,
        "deployment_mode": MODE,
        "deployment_label": _deployment_label(),
        "control_url": CONTROL or None,
        "version": "4.1.0",
        "global": cfg.get("global"),
        "zones_count": len(cfg.get("zones") or []),
        "custom_rules_count": len(cfg.get("custom_waf_rules") or []),
        "ngfw_policies": len((((cfg.get("global") or {}).get("ngfw") or {}).get("policies") or [])),
        "containers": _docker_ps(),
        "access": stats,
        "crowdsec_decision_count": len(decisions),
        "features": [
            "security_levels",
            "managed_waf_owasp_crs",
            "custom_waf_rules",
            "ip_access_rules",
            "bot_fight_mode",
            "under_attack_mode",
            "rate_limiting_enforced",
            "ssl_modes",
            "caching",
            "analytics",
            "hybrid_multitenant",
            "strong_tenant_isolation",
            "unknown_host_deny",
            "host_scoped_firewall",
            "ngfw_policies",
            "url_filtering",
            "dns_filter",
            "domain_blocklists",
            "category_feeds",
            "ransomware_defense",
            "security_profiles",
            "file_blocking",
            "anti_spyware",
            "external_dynamic_lists",
            "app_control",
            "geo_blocking",
            "address_objects",
            "api_shield",
            "graphql_guard",
            "page_shield",
            "waiting_room",
            "virtual_patching",
            "auth_hardening",
            "sensitive_data_egress",
            "honeypot",
            "advanced_bot_pow",
            "leaked_credentials_hibp",
            "logpush",
            "mtls_stub",
        ],
        "dns_filter": (dnsf.feed_status() if dnsf else None),
        "ransomware_defense": rw_pol,
    }


@app.get("/api/isolation")
def isolation_status(_: str = Depends(_auth)):
    cfg = ec.load_config()
    tmap = ti.load_tenant_map() if ti else {}
    return {
        "mode": MODE,
        "deployment_label": _deployment_label(),
        "pinned_tenant": PINNED_TENANT or None,
        "unknown_host_policy": "deny_421",
        "default_origin_fallthrough": False,
        "firewall_scope": "per_zone_host",
        "custom_rules_scope": "host_or_tenant",
        "tenant_map_entries": len(tmap),
        "tenants": sorted(set(tmap.values())),
        "zones": len(cfg.get("zones") or []),
        "strong_isolation": True,
        "shared_offering": False,
        "note": "This appliance is dedicated to one organization. Unknown hosts are denied.",
    }


@app.get("/api/config")
def get_config(tenant: Optional[str] = None, _: str = Depends(_auth)):
    cfg = ec.load_config()
    if ti and (tenant or (MODE == "dedicated" and PINNED_TENANT)):
        return ti.filter_config_view(
            cfg, tenant or PINNED_TENANT, mssp_admin=not tenant and MODE != "dedicated"
        )
    return cfg


@app.put("/api/config/global")
def put_global(body: GlobalSettingsIn, _: str = Depends(_auth)):
    cfg = ec.load_config()
    g = cfg.setdefault("global", deepcopy(ec.DEFAULT_GLOBAL))
    data = body.model_dump(exclude_none=True)
    if "security_level" in data and data["security_level"] not in ec.SECURITY_LEVELS:
        raise HTTPException(400, detail=f"security_level must be one of {ec.SECURITY_LEVELS}")
    g.update(data)
    result = ec.apply_all(cfg)
    return {"ok": True, "global": g, "apply": result}


@app.get("/api/zones")
def list_zones(tenant: Optional[str] = None, _: str = Depends(_auth)):
    cfg = ec.load_config()
    zones = cfg.get("zones") or []
    scope = (tenant or (PINNED_TENANT if MODE == "dedicated" else "") or "").upper()
    if scope:
        zones = [z for z in zones if (z.get("tenant_short_code") or "").upper() == scope]
    return {"zones": zones, "tenant_scope": scope or None}


@app.post("/api/zones")
def create_or_update_zone(body: ZoneIn, _: str = Depends(_auth)):
    payload = body.model_dump()
    if payload.get("security_level") and payload["security_level"] not in ec.SECURITY_LEVELS:
        raise HTTPException(400, detail="invalid security_level")
    if not (payload.get("tenant_short_code") or "").strip():
        if MODE == "dedicated" and PINNED_TENANT:
            payload["tenant_short_code"] = PINNED_TENANT
        else:
            raise HTTPException(400, detail="tenant_short_code required for multi-tenant isolation")
    if MODE == "dedicated" and PINNED_TENANT:
        if payload["tenant_short_code"].upper() != PINNED_TENANT:
            raise HTTPException(403, detail=f"dedicated edge pinned to {PINNED_TENANT}")
    try:
        result = ec.upsert_zone(payload)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return {"ok": True, "apply": result, "zones": ec.load_config().get("zones")}


@app.patch("/api/zones/{hostname}")
def patch_zone(hostname: str, body: Dict[str, Any], _: str = Depends(_auth)):
    body = dict(body or {})
    body["public_hostname"] = hostname
    cfg = ec.load_config()
    existing = next(
        (z for z in cfg.get("zones") or [] if (z.get("public_hostname") or "").lower() == hostname.lower()),
        None,
    )
    if not existing:
        raise HTTPException(404, detail="Zone not found")
    if MODE == "dedicated" and PINNED_TENANT:
        if (existing.get("tenant_short_code") or "").upper() != PINNED_TENANT:
            raise HTTPException(403, detail="cross-tenant zone denied")
    if not body.get("origin_url"):
        body["origin_url"] = existing.get("origin_url")
    if not body.get("tenant_short_code"):
        body["tenant_short_code"] = existing.get("tenant_short_code")
    merged = {**existing, **body}
    result = ec.upsert_zone(merged)
    return {"ok": True, "apply": result}


@app.delete("/api/zones/{hostname}")
def remove_zone(hostname: str, _: str = Depends(_auth)):
    cfg = ec.load_config()
    existing = next(
        (z for z in cfg.get("zones") or [] if (z.get("public_hostname") or "").lower() == hostname.lower()),
        None,
    )
    if existing and MODE == "dedicated" and PINNED_TENANT:
        if (existing.get("tenant_short_code") or "").upper() != PINNED_TENANT:
            raise HTTPException(403, detail="cross-tenant zone denied")
    return ec.delete_zone(hostname)


@app.get("/api/waf/rules")
def list_custom_rules(tenant: Optional[str] = None, _: str = Depends(_auth)):
    cfg = ec.load_config()
    rules = cfg.get("custom_waf_rules") or []
    scope = (tenant or (PINNED_TENANT if MODE == "dedicated" else "") or "").upper()
    if scope and ti:
        view = ti.filter_config_view(cfg, scope, mssp_admin=False)
        rules = view.get("custom_waf_rules") or []
    return {"rules": rules, "tenant_scope": scope or None}


@app.post("/api/waf/rules")
def add_custom_rule(body: CustomRuleIn, _: str = Depends(_auth)):
    cfg = ec.load_config()
    rules = cfg.setdefault("custom_waf_rules", [])
    rule = body.model_dump()
    rule["id"] = body.id or ec.new_id()
    if MODE == "dedicated" and PINNED_TENANT:
        rule["tenant_short_code"] = PINNED_TENANT
    if ti:
        try:
            rule = ti.validate_custom_rule_scope(rule, mssp_admin=True)
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from exc
    if not rule.get("public_hostname") and not rule.get("tenant_short_code"):
        raise HTTPException(
            400,
            detail="public_hostname or tenant_short_code required (multi-tenant isolation)",
        )
    rules = [r for r in rules if r.get("id") != rule["id"]]
    rules.append(rule)
    rules.sort(key=lambda r: int(r.get("priority") or 100))
    cfg["custom_waf_rules"] = rules
    apply = ec.apply_all(cfg)
    return {"ok": True, "rule": rule, "apply": apply}


@app.delete("/api/waf/rules/{rule_id}")
def delete_custom_rule(rule_id: str, _: str = Depends(_auth)):
    cfg = ec.load_config()
    cfg["custom_waf_rules"] = [r for r in (cfg.get("custom_waf_rules") or []) if r.get("id") != rule_id]
    return {"ok": True, "apply": ec.apply_all(cfg)}


@app.post("/api/apply")
def apply_config(_: str = Depends(_auth)):
    return ec.apply_all()


@app.get("/api/analytics")
def analytics(tenant: Optional[str] = None, _: str = Depends(_auth)):
    stats = _parse_access_stats(1000)
    recent = stats["recent"][:50]
    scope = (tenant or (PINNED_TENANT if MODE == "dedicated" else "") or "").upper()
    if scope and ti:
        tmap = ti.load_tenant_map() or ti.build_tenant_map(ec.load_config())
        allowed_hosts = {h for h, t in tmap.items() if t == scope}
        recent = [
            r
            for r in recent
            if (r.get("host") or "").lower().split(":")[0] in allowed_hosts
        ]
        # recompute block count for scope
        blocks = sum(1 for r in recent if r.get("status") == 403)
        return {
            "requests_sampled": len(recent),
            "threats_blocked": blocks,
            "status_breakdown": stats["by_status"],
            "recent": recent,
            "tenant_scope": scope,
            "crowdsec_decisions": _crowdsec_decisions()[:30],
            "note": "NikTiar Bot Defense decisions are IP-scoped on this dedicated edge.",
        }
    return {
        "requests_sampled": stats["total_sampled"],
        "threats_blocked": stats["waf_blocks_403"],
        "status_breakdown": stats["by_status"],
        "recent": recent,
        "crowdsec_decisions": _crowdsec_decisions()[:30],
    }


@app.get("/api/crowdsec")
def crowdsec_view(_: str = Depends(_auth)):
    return {"decisions": _crowdsec_decisions()[:100]}


@app.post("/api/reload")
def reload_only(_: str = Depends(_auth)):
    return ec.reload_caddy()


@app.get("/api/security-profiles")
def get_security_profiles(_: str = Depends(_auth)):
    if not secprof:
        raise HTTPException(503, detail="Security Profiles module unavailable")
    return {
        "policy": secprof.load_policy(),
        "catalog": secprof.catalog(),
        "edl_dir": str(RUNTIME / "edl"),
    }


@app.put("/api/security-profiles")
def put_security_profiles(body: Dict[str, Any], _: str = Depends(_auth)):
    if not secprof:
        raise HTTPException(503, detail="Security Profiles module unavailable")
    pol = secprof.load_policy()
    if body.get("preset") and body["preset"] != pol.get("preset"):
        pol = secprof.apply_preset(str(body["preset"]))
    for section in (
        "file_blocking",
        "anti_spyware",
        "url_filtering",
        "vulnerability_protection",
        "edl",
        "sandbox",
    ):
        if isinstance(body.get(section), dict):
            pol[section] = {**(pol.get(section) or {}), **body[section]}
    for k in ("enabled", "notes", "preset"):
        if k in body and k != "preset":
            pol[k] = body[k]
        elif k == "preset" and body.get("preset"):
            pol["preset"] = body["preset"]
    if body.get("_customized"):
        pol["_customized"] = True
    cfg = ec.load_config()
    result = secprof.apply_security_profiles(cfg, pol)
    apply = ec.apply_all(cfg)
    return {
        "ok": True,
        "profiles": result,
        "apply": {"ok": apply.get("ok"), "security_profiles": apply.get("security_profiles")},
    }


@app.post("/api/security-profiles/preset/{name}")
def security_profiles_preset(name: str, _: str = Depends(_auth)):
    if not secprof:
        raise HTTPException(503, detail="Security Profiles module unavailable")
    pol = secprof.apply_preset(name)
    cfg = ec.load_config()
    result = secprof.apply_security_profiles(cfg, pol)
    apply = ec.apply_all(cfg)
    return {"ok": True, "policy": pol, "result": result, "apply": apply}


@app.get("/api/ransomware-defense")
def get_ransomware_defense(_: str = Depends(_auth)):
    if not rwd:
        raise HTTPException(503, detail="Ransomware Defense module unavailable")
    ransom_count = 0
    try:
        p = RUNTIME / "dns-feeds" / "ransomware.txt"
        if p.exists():
            ransom_count = sum(
                1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")
            )
    except Exception:  # noqa: BLE001
        pass
    cat = rwd.catalog()
    # Customer-facing API: omit internal sell/SLA claim lists if present on policy.
    pol = dict(rwd.load_policy())
    pol.pop("sellable_claims", None)
    pol.pop("never_claim", None)
    return {
        "policy": pol,
        "catalog": cat,
        "dns_ransomware_domains": ransom_count,
        "summary": cat.get("summary"),
    }


@app.put("/api/ransomware-defense")
def put_ransomware_defense(body: Dict[str, Any], _: str = Depends(_auth)):
    if not rwd:
        raise HTTPException(503, detail="Ransomware Defense module unavailable")
    pol = rwd.load_policy()
    for k in (
        "enabled",
        "mode",
        "dns_category",
        "block_ransom_note_paths",
        "block_double_extension_downloads",
        "block_script_droppers",
        "block_archive_droppers",
        "block_webdav_write",
        "block_tor2web_gateways",
        "block_suspicious_exfil_paths",
        "notes",
    ):
        if k in (body or {}):
            pol[k] = body[k]
    cfg = ec.load_config()
    result = rwd.apply_ransomware_defense(cfg, pol)
    apply = ec.apply_all(cfg)
    return {"ok": True, "ransomware": result, "apply": {"ok": apply.get("ok"), "ransomware_defense": apply.get("ransomware_defense")}}


@app.get("/api/dns-filter/catalog")
def dns_filter_catalog(_: str = Depends(_auth)):
    if not dnsf:
        raise HTTPException(503, detail="DNS Filter module unavailable")
    return dnsf.catalog()


@app.get("/api/dns-filter")
def get_dns_filter(_: str = Depends(_auth)):
    if not dnsf:
        raise HTTPException(503, detail="DNS Filter module unavailable")
    return {
        "policy": dnsf.load_policy(),
        "status": dnsf.feed_status(),
        "catalog": dnsf.catalog(),
    }


@app.put("/api/dns-filter")
def put_dns_filter(body: Dict[str, Any], _: str = Depends(_auth)):
    if not dnsf:
        raise HTTPException(503, detail="DNS Filter module unavailable")
    pol = dnsf.load_policy()
    for k in (
        "enabled",
        "enabled_categories",
        "custom_block_domains",
        "custom_allow_domains",
        "waf_host_block",
        "sinkhole_ip",
        "notes",
    ):
        if k in (body or {}):
            pol[k] = body[k]
    # Normalize domains
    if isinstance(pol.get("custom_block_domains"), list):
        pol["custom_block_domains"] = [
            d for d in (dnsf.normalize_domain(str(x)) for x in pol["custom_block_domains"]) if d
        ]
    if isinstance(pol.get("custom_allow_domains"), list):
        pol["custom_allow_domains"] = [
            d for d in (dnsf.normalize_domain(str(x)) for x in pol["custom_allow_domains"]) if d
        ]
    if isinstance(pol.get("enabled_categories"), list):
        pol["enabled_categories"] = [
            str(c) for c in pol["enabled_categories"] if str(c) in dnsf.DEFAULT_CATEGORIES
        ]
    result = dnsf.apply_dns_filter(pol)
    # Reload WAF so Host-header rules take effect
    waf_apply = ec.apply_all(ec.load_config())
    return {"ok": True, "dns": result, "waf_apply": {"ok": waf_apply.get("ok"), "dns_filter": waf_apply.get("dns_filter")}}


@app.post("/api/dns-filter/resync")
def dns_filter_resync(_: str = Depends(_auth)):
    if not dnsf:
        raise HTTPException(503, detail="DNS Filter module unavailable")
    sync = dnsf.trigger_feed_resync()
    dns = dnsf.reload_dns_engine()
    waf = dnsf.write_waf_host_rules()
    return {"ok": bool(sync.get("ok")), "sync": sync, "dns_reload": dns, "waf": waf}


@app.get("/api/ngfw/catalog")
def ngfw_catalog(_: str = Depends(_auth)):
    if not ngfw:
        raise HTTPException(503, detail="NGFW module unavailable")
    return ngfw.catalog()


@app.get("/api/ngfw")
def get_ngfw(_: str = Depends(_auth)):
    cfg = ec.load_config()
    if ngfw:
        ngfw.merge_ngfw(cfg)
    return {
        "ngfw": ((cfg.get("global") or {}).get("ngfw") or {}),
        "catalog": ngfw.catalog() if ngfw else {},
        "help": (ngfw.catalog().get("help") if ngfw else {}),
    }


@app.put("/api/ngfw")
def put_ngfw(body: Dict[str, Any], _: str = Depends(_auth)):
    """Replace or merge the global NGFW pack (policies, URL filter, geo, objects)."""
    cfg = ec.load_config()
    if ngfw:
        ngfw.merge_ngfw(cfg)
    g = cfg.setdefault("global", {})
    current = g.setdefault("ngfw", {})
    for k, v in (body or {}).items():
        if k in ("policies", "address_objects", "url_objects") and isinstance(v, list):
            current[k] = v
        elif k == "url_filter" and isinstance(v, dict):
            current["url_filter"] = {**(current.get("url_filter") or {}), **v}
        elif k == "geo_block" and isinstance(v, dict):
            current["geo_block"] = {**(current.get("geo_block") or {}), **v}
        else:
            current[k] = v
    result = ec.apply_all(cfg)
    return {"ok": True, "ngfw": current, "apply": result}


@app.post("/api/ngfw/policies")
def add_ngfw_policy(body: Dict[str, Any], _: str = Depends(_auth)):
    cfg = ec.load_config()
    if ngfw:
        ngfw.merge_ngfw(cfg)
    policies = ((cfg.setdefault("global", {})).setdefault("ngfw", {})).setdefault("policies", [])
    pol = dict(body or {})
    pol["id"] = pol.get("id") or (ngfw.new_policy_id() if ngfw else secrets.token_hex(6))
    pol.setdefault("enabled", True)
    pol.setdefault("priority", 100)
    pol.setdefault("action", "deny")
    pol.setdefault("source", "any")
    pol.setdefault("zone", "*")
    policies.append(pol)
    result = ec.apply_all(cfg)
    return {"ok": True, "policy": pol, "apply": result}


@app.delete("/api/ngfw/policies/{policy_id}")
def del_ngfw_policy(policy_id: str, _: str = Depends(_auth)):
    cfg = ec.load_config()
    ng = (cfg.setdefault("global", {})).setdefault("ngfw", {})
    ng["policies"] = [p for p in (ng.get("policies") or []) if p.get("id") != policy_id]
    result = ec.apply_all(cfg)
    return {"ok": True, "apply": result}


@app.post("/api/ngfw/objects/address")
def add_address_object(body: Dict[str, Any], _: str = Depends(_auth)):
    cfg = ec.load_config()
    if ngfw:
        ngfw.merge_ngfw(cfg)
    objs = ((cfg.setdefault("global", {})).setdefault("ngfw", {})).setdefault("address_objects", [])
    obj = dict(body or {})
    obj["id"] = obj.get("id") or (ngfw.new_object_id("obj") if ngfw else secrets.token_hex(4))
    obj.setdefault("type", "cidr")
    obj.setdefault("values", [])
    objs.append(obj)
    ec.save_config(cfg)
    return {"ok": True, "object": obj}


@app.get("/api/enterprise")
def get_enterprise(_: str = Depends(_auth)):
    cfg = ec.load_config()
    return {
        "enterprise": (cfg.get("global") or {}).get("enterprise") or {},
        "catalog": [
            {"id": "api_shield", "name": "API Shield", "cf": "API Shield"},
            {"id": "graphql_guard", "name": "GraphQL Guard", "cf": "API abuse / GraphQL"},
            {"id": "page_shield", "name": "Page Shield", "cf": "Page Shield / CSP"},
            {"id": "waiting_room", "name": "Waiting Room", "cf": "Waiting Room"},
            {"id": "virtual_patching", "name": "Virtual Patching", "cf": "WAF Managed + CVE paths"},
            {"id": "auth_hardening", "name": "Auth Hardening", "cf": "Credential stuffing defenses"},
            {"id": "sensitive_data_egress", "name": "Sensitive Data Detection", "cf": "DLP / API Shield SDS"},
            {"id": "honeypot", "name": "Honeypot Paths", "cf": "Deception"},
            {"id": "advanced_bot", "name": "Advanced Bot / PoW", "cf": "Bot Management"},
            {"id": "leaked_credentials", "name": "Leaked Credentials", "cf": "Leaked credential checks"},
            {"id": "logpush", "name": "Logpush", "cf": "Logpush / SIEM"},
            {"id": "mtls", "name": "mTLS", "cf": "API Shield mTLS"},
        ],
    }


@app.put("/api/enterprise")
def put_enterprise(body: Dict[str, Any], _: str = Depends(_auth)):
    cfg = ec.load_config()
    g = cfg.setdefault("global", {})
    ent = g.setdefault("enterprise", {})
    # shallow+one-level merge
    for k, v in (body or {}).items():
        if isinstance(v, dict) and isinstance(ent.get(k), dict):
            ent[k] = {**ent[k], **v}
        else:
            ent[k] = v
    result = ec.apply_all(cfg)
    return {"ok": True, "enterprise": ent, "apply": result}


@app.post("/api/enterprise/hibp-check")
async def hibp_check(payload: Dict[str, Any], _: str = Depends(_auth)):
    """Have I Been Pwned k-anonymity check for a password (enterprise leaked-cred)."""
    import hashlib

    import httpx

    password = str(payload.get("password") or "")
    if len(password) < 6:
        raise HTTPException(400, detail="password too short")
    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"https://api.pwnedpasswords.com/range/{prefix}",
                headers={"Add-Padding": "true", "User-Agent": "NikTiar-SecureEdge"},
            )
            r.raise_for_status()
        count = 0
        for line in r.text.splitlines():
            parts = line.split(":")
            if len(parts) == 2 and parts[0].upper() == suffix:
                count = int(parts[1].strip())
                break
        return {"pwned": count > 0, "count": count, "mode": "k-anonymity"}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, detail=f"HIBP unreachable: {exc}") from exc


@app.post("/api/enterprise/logpush/test")
async def logpush_test(_: str = Depends(_auth)):
    cfg = ec.load_config()
    lp = ((cfg.get("global") or {}).get("enterprise") or {}).get("logpush") or {}
    url = (lp.get("webhook_url") or "").strip()
    if not url:
        raise HTTPException(400, detail="logpush.webhook_url not set")
    import httpx

    sample = {
        "source": "niktiar-secure-edge",
        "hostname": HOST,
        "event_type": "logpush_test",
        "severity": "info",
        "summary": "NikTiar Logpush test event",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(url, json=sample)
    return {"ok": r.status_code < 300, "status": r.status_code}
