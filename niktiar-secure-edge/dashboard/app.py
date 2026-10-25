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
        "version": "2.0.0",
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
        ],
    }


@app.get("/api/config")
def get_config(_: str = Depends(_auth)):
    return ec.load_config()


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
def list_zones(_: str = Depends(_auth)):
    return {"zones": ec.load_config().get("zones") or []}


@app.post("/api/zones")
def create_or_update_zone(body: ZoneIn, _: str = Depends(_auth)):
    payload = body.model_dump()
    if payload.get("security_level") and payload["security_level"] not in ec.SECURITY_LEVELS:
        raise HTTPException(400, detail="invalid security_level")
    try:
        result = ec.upsert_zone(payload)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return {"ok": True, "apply": result, "zones": ec.load_config().get("zones")}


@app.patch("/api/zones/{hostname}")
def patch_zone(hostname: str, body: Dict[str, Any], _: str = Depends(_auth)):
    body = dict(body or {})
    body["public_hostname"] = hostname
    # Keep origin if not provided
    cfg = ec.load_config()
    existing = next(
        (z for z in cfg.get("zones") or [] if (z.get("public_hostname") or "").lower() == hostname.lower()),
        None,
    )
    if not existing:
        raise HTTPException(404, detail="Zone not found")
    if not body.get("origin_url"):
        body["origin_url"] = existing.get("origin_url")
    merged = {**existing, **body}
    result = ec.upsert_zone(merged)
    return {"ok": True, "apply": result}


@app.delete("/api/zones/{hostname}")
def remove_zone(hostname: str, _: str = Depends(_auth)):
    return ec.delete_zone(hostname)


@app.get("/api/waf/rules")
def list_custom_rules(_: str = Depends(_auth)):
    return {"rules": ec.load_config().get("custom_waf_rules") or []}


@app.post("/api/waf/rules")
def add_custom_rule(body: CustomRuleIn, _: str = Depends(_auth)):
    cfg = ec.load_config()
    rules = cfg.setdefault("custom_waf_rules", [])
    rule = body.model_dump()
    rule["id"] = body.id or ec.new_id()
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
def analytics(_: str = Depends(_auth)):
    stats = _parse_access_stats(1000)
    return {
        "requests_sampled": stats["total_sampled"],
        "threats_blocked": stats["waf_blocks_403"],
        "status_breakdown": stats["by_status"],
        "recent": stats["recent"][:50],
        "crowdsec_decisions": _crowdsec_decisions()[:30],
    }


@app.get("/api/crowdsec")
def crowdsec_view(_: str = Depends(_auth)):
    return {"decisions": _crowdsec_decisions()[:100]}


@app.post("/api/reload")
def reload_only(_: str = Depends(_auth)):
    return ec.reload_caddy()
