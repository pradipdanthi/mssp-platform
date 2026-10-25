"""NikTiar Secure Edge — Cloudflare-parity appliance dashboard."""
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
MODE = (os.getenv("SECURE_EDGE_MODE") or "shared").lower()
DASH_USER = os.getenv("EDGE_DASHBOARD_USER") or "admin"
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

app = FastAPI(title="NikTiar Secure Edge", version="2.0.0")
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(static_dir)), name="assets")


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
    return {"ok": True, "service": "secure-edge-dashboard", "version": "2.0.0", "hostname": HOST}


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
    return {
        "hostname": HOST,
        "deployment_mode": MODE,
        "control_url": CONTROL or None,
        "version": "3.0.0",
        "global": cfg.get("global"),
        "zones_count": len(cfg.get("zones") or []),
        "custom_rules_count": len(cfg.get("custom_waf_rules") or []),
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
            "rate_limiting",
            "ssl_modes",
            "caching",
            "analytics",
            "hybrid_multitenant",
            "strong_tenant_isolation",
            "unknown_host_deny",
            "host_scoped_firewall",
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
    }


@app.get("/api/isolation")
def isolation_status(_: str = Depends(_auth)):
    cfg = ec.load_config()
    tmap = ti.load_tenant_map() if ti else {}
    return {
        "mode": MODE,
        "pinned_tenant": PINNED_TENANT or None,
        "unknown_host_policy": "deny_421",
        "default_origin_fallthrough": False,
        "firewall_scope": "per_zone_host",
        "custom_rules_scope": "host_or_tenant",
        "tenant_map_entries": len(tmap),
        "tenants": sorted(set(tmap.values())),
        "zones": len(cfg.get("zones") or []),
        "strong_isolation": True,
        "note": (
            "Shared = soft multi-tenant with Host-scoped policies + unknown-host deny. "
            "Dedicated = single-tenant pin via NIKTIAR_TENANT_CODE."
        ),
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
            "note": "CrowdSec decisions are IP-global on shared edges (security side-effect, not data leak).",
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
