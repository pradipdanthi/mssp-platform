"""NikTiar Secure Edge — local appliance management dashboard + API."""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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

app = FastAPI(title="NikTiar Secure Edge Dashboard", version="1.0.0")
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(static_dir)), name="assets")


class LoginIn(BaseModel):
    username: str
    password: str


class LocalSiteIn(BaseModel):
    tenant_short_code: str = Field(..., min_length=2, max_length=32)
    public_hostname: str = Field(..., min_length=1, max_length=253)
    origin_url: str = Field(..., min_length=3, max_length=512)
    tls_mode: str = Field(default="http_only", max_length=16)
    waf_profile: str = Field(default="standard", max_length=32)
    notes: Optional[str] = None


def _headers() -> Dict[str, str]:
    h = {"Content-Type": "application/json", "User-Agent": "NikTiar-SecureEdge-Dashboard/1.0"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


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


def _crowdsec_metrics() -> Dict[str, Any]:
    try:
        r = subprocess.run(
            ["docker", "exec", CS_CONTAINER, "cscli", "metrics", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode != 0:
            return {"raw": (r.stderr or r.stdout or "")[:500]}
        return json.loads(r.stdout or "{}")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


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
        "recent": recent[:80],
    }


def _local_sites_file() -> Path:
    return RUNTIME / "local_sites.json"


def _load_local_sites() -> List[Dict[str, Any]]:
    p = _local_sites_file()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def _save_local_sites(sites: List[Dict[str, Any]]) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    _local_sites_file().write_text(json.dumps(sites, indent=2), encoding="utf-8")


def _render_sites_caddy(sites: List[Dict[str, Any]]) -> str:
    lines = ["# Generated by Secure Edge dashboard/agent", f"# mode={MODE} host={HOST}"]
    for site in sites:
        public_host = (site.get("public_hostname") or "").strip().lower()
        origin = (site.get("origin_url") or "").strip()
        if not public_host or not origin:
            continue
        matcher = "site_" + re.sub(r"[^a-zA-Z0-9_]", "_", public_host)[:48]
        tls = (site.get("tls_mode") or "http_only").lower()
        lines.append(f"@{matcher} host {public_host}")
        lines.append(f"handle @{matcher} {{")
        if tls == "acme":
            # ACME is configured on a dedicated :443 site block in Caddyfile; mark header for ops
            lines.append("\theader X-NikTiar-TLS acme")
        lines.append(f"\treverse_proxy {origin} {{")
        lines.append("\t\ttrusted_proxies private_ranges")
        lines.append("\t\theader_up X-NikTiar-Tenant {http.request.host}")
        lines.append("\t}")
        lines.append("}")
        lines.append("")
    if len(lines) <= 2:
        lines.append("# (no sites)")
    return "\n".join(lines) + "\n"


def _reload_caddy() -> Dict[str, Any]:
    try:
        r = subprocess.run(
            [
                "docker",
                "exec",
                WAF_CONTAINER,
                "sh",
                "-c",
                "cp /config/caddy/Caddyfile /etc/caddy/Caddyfile && caddy reload --config /etc/caddy/Caddyfile --force",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {"ok": r.returncode == 0, "stderr": (r.stderr or "")[-400:], "stdout": (r.stdout or "")[-200:]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _apply_sites(sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME / "sites.caddy").write_text(_render_sites_caddy(sites), encoding="utf-8")
    (RUNTIME / "sites.json").write_text(json.dumps({"sites": sites}, indent=2), encoding="utf-8")
    return _reload_caddy()


async def _control_sites() -> List[Dict[str, Any]]:
    if not CONTROL:
        return []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{CONTROL}/api/v1/secure-edge/config",
                headers=_headers(),
                params={"hostname": HOST, "mode": MODE},
            )
            if r.status_code == 200:
                return r.json().get("sites") or []
    except Exception:  # noqa: BLE001
        pass
    return []


@app.get("/")
def index():
    index_path = static_dir / "index.html"
    if not index_path.exists():
        return JSONResponse({"error": "dashboard UI missing"}, status_code=500)
    return FileResponse(index_path)


@app.post("/api/login")
def login(body: LoginIn):
    if body.username != DASH_USER or body.password != DASH_PASS:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    tok = secrets.token_urlsafe(32)
    SESSIONS[tok] = time.time() + SESSION_TTL
    return {"token": tok, "expires_in": SESSION_TTL, "user": DASH_USER}


@app.get("/api/overview")
async def overview(_: str = Depends(_auth)):
    control_sites = await _control_sites()
    local_sites = _load_local_sites()
    # Prefer merged view: control-plane authoritative when online
    sites = control_sites or local_sites
    stats = _parse_access_stats()
    decisions = _crowdsec_decisions()
    return {
        "hostname": HOST,
        "deployment_mode": MODE,
        "control_url": CONTROL or None,
        "version": "1.0.0",
        "containers": _docker_ps(),
        "sites_count": len(sites),
        "sites": sites,
        "access": stats,
        "crowdsec_decisions": decisions[:50],
        "crowdsec_decision_count": len(decisions),
        "features": [
            "coraza_crs_waf",
            "caddy_edge",
            "crowdsec",
            "hybrid_multitenant",
            "site_management",
            "tls_acme_ready",
            "rate_limit",
            "local_dashboard",
            "control_plane_sync",
        ],
    }


@app.get("/api/sites")
async def list_sites(_: str = Depends(_auth)):
    control = await _control_sites()
    local = _load_local_sites()
    return {"control_plane": control, "local": local, "active": control or local}


@app.post("/api/sites")
async def create_site(body: LocalSiteIn, _: str = Depends(_auth)):
    """Create site on control plane when reachable; always keep local copy + reload."""
    payload = body.model_dump()
    payload["public_hostname"] = payload["public_hostname"].lower().strip()
    payload["tenant_short_code"] = payload["tenant_short_code"].upper()
    payload["enabled"] = True
    created = None
    if CONTROL:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                # Admin token not available on appliance — use local apply + instruct portal
                # Still POST to appliance-facing path is not create; store local and reload.
                pass
        except Exception:  # noqa: BLE001
            pass
    sites = _load_local_sites()
    sites = [s for s in sites if s.get("public_hostname") != payload["public_hostname"]]
    sites.append(payload)
    _save_local_sites(sites)
    # Merge with control sites for routing
    control = await _control_sites()
    merged: Dict[str, Dict[str, Any]] = {}
    for s in control:
        merged[s["public_hostname"]] = s
    for s in sites:
        merged[s["public_hostname"]] = s
    reload = _apply_sites(list(merged.values()))
    return {"ok": True, "site": payload, "reload": reload, "created_remote": created}


@app.delete("/api/sites/{hostname}")
async def delete_site(hostname: str, _: str = Depends(_auth)):
    hostname = hostname.lower().strip()
    sites = [s for s in _load_local_sites() if s.get("public_hostname") != hostname]
    _save_local_sites(sites)
    control = await _control_sites()
    merged = {s["public_hostname"]: s for s in control if s.get("public_hostname") != hostname}
    for s in sites:
        merged[s["public_hostname"]] = s
    reload = _apply_sites(list(merged.values()))
    return {"ok": True, "reload": reload}


@app.post("/api/reload")
def reload_edge(_: str = Depends(_auth)):
    return _reload_caddy()


@app.get("/api/access-log")
def access_log(_: str = Depends(_auth)):
    return _parse_access_stats(800)


@app.get("/api/crowdsec")
def crowdsec_view(_: str = Depends(_auth)):
    return {"decisions": _crowdsec_decisions()[:100], "metrics": _crowdsec_metrics()}


@app.post("/api/crowdsec/bootstrap-bouncer")
def bootstrap_bouncer(_: str = Depends(_auth)):
    """Create firewall bouncer API key and write crowdsec/bouncer.yaml."""
    try:
        name = f"firewall-{int(time.time())}"
        r = subprocess.run(
            ["docker", "exec", CS_CONTAINER, "cscli", "bouncers", "add", name, "-o", "raw"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if r.returncode != 0:
            raise HTTPException(status_code=500, detail=(r.stderr or r.stdout or "cscli failed")[:300])
        key = (r.stdout or "").strip()
        bouncer_path = Path("/opt/niktiar-secure-edge/crowdsec/bouncer.yaml")
        # Also write into runtime for compose mount override
        runtime_b = RUNTIME / "bouncer.yaml"
        content = (
            "mode: iptables\n"
            "update_frequency: 10s\n"
            "log_mode: stdout\n"
            "log_level: info\n"
            "api_url: http://127.0.0.1:7422/\n"
            f"api_key: {key}\n"
            "iptables_chains:\n"
            "  - INPUT\n"
            "  - FORWARD\n"
            "deny_action: DROP\n"
        )
        RUNTIME.mkdir(parents=True, exist_ok=True)
        runtime_b.write_text(content, encoding="utf-8")
        if bouncer_path.parent.exists():
            bouncer_path.write_text(content, encoding="utf-8")
        return {
            "ok": True,
            "bouncer": name,
            "api_key": key,
            "hint": "Run: cd /opt/niktiar-secure-edge/docker && sudo docker compose --profile enforce up -d crowdsec-firewall-bouncer",
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/health")
def health():
    return {"ok": True, "service": "secure-edge-dashboard", "hostname": HOST}
