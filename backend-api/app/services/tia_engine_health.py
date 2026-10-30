"""Layered, honest engine health for TIA.

An open TCP port is not a healthy service. Every engine is observed in separate layers:

    reachability  the host answers on the service port
    api           the HTTP interface answers sensibly
    auth          OUR credentials are accepted
    application   the service itself reports healthy (daemons running, queue ok, ...)
    telemetry     the engine is still producing data we ingest (freshness)

Each layer is ``ok | degraded | unreachable | unauthorized | unknown`` with a machine reason.
``unknown`` means "no adapter or no evidence", never "fine". The roll-up never turns missing
evidence into ``ok``: an engine that is only known to have an open port reports ``unknown``.

Every observation records scope, source, checked_at and whether it came from cache. Cached
results are labelled with their age. A probe that exceeds its deadline is reported as such and
cannot stall the others.

This module only reads. It never changes an engine.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

LAYERS = ("reachability", "api", "auth", "application", "telemetry")
PRIVILEGED_ROLES = ("platform_admin", "soc_manager")

_lock = threading.Lock()
_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tia-health")


def _ttl() -> float:
    return float(os.getenv("TIA_ENGINE_HEALTH_TTL_SECONDS", "30") or 30)


def _deadline() -> float:
    return float(os.getenv("TIA_ENGINE_HEALTH_DEADLINE_SECONDS", "8") or 8)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _layer(status: str, reason: Optional[str] = None, source: str = "", detail: Optional[str] = None) -> Dict[str, Any]:
    return {"status": status, "reason": reason, "source": source, "detail": detail, "checked_at": _now_iso()}


def _unknown(reason: str, source: str = "") -> Dict[str, Any]:
    return _layer("unknown", reason, source)


# --------------------------------------------------------------------------
# individual probes (each returns a layer dict; none raises)
# --------------------------------------------------------------------------

def probe_reachability(host: str, port: int) -> Dict[str, Any]:
    from app.services.soc_console_engines import _tcp_probe

    r = _tcp_probe(host, int(port), timeout=float(os.getenv("TIA_HEALTH_TCP_TIMEOUT", "1.5")))
    if r["reachable"]:
        return _layer("ok", None, "tcp_connect", f"{r['latency_ms']} ms")
    return _layer("unreachable", "connection_failed", "tcp_connect", r.get("error"))


def _http_status(url: str, *, headers: Optional[Dict[str, str]] = None, timeout: float = 3.0, context: Any = None) -> Tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return resp.status, resp.read(65536).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception as exc:  # noqa: BLE001
        raise ConnectionError(type(exc).__name__) from exc


def probe_telemetry(sources: List[str], *, expect_continuous: bool, stale_minutes: int) -> Dict[str, Any]:
    from app.db.session import fetch_one

    if not sources:
        return _unknown("no_telemetry_source", "database")
    try:
        row = fetch_one(
            "SELECT extract(epoch FROM (now() - max(created_at)))::bigint AS age_s, count(*)::bigint AS n "
            "FROM security_alerts WHERE lower(coalesce(source_tool,'')) = ANY(%s);",
            (sources,),
        ) or {}
    except Exception as exc:  # noqa: BLE001
        return _unknown("database_error", "database") | {"detail": type(exc).__name__}
    if row.get("age_s") is None:
        return _unknown("no_events_recorded", "database")
    age = int(row["age_s"])
    fresh = age <= stale_minutes * 60
    if fresh:
        return _layer("ok", None, "database", f"last event {age}s ago")
    if expect_continuous:
        return _layer("degraded", "telemetry_stale", "database", f"last event {age}s ago; expected within {stale_minutes} min")
    return _layer("unknown", "no_recent_events", "database", f"last event {age}s ago (a quiet source is not proof of failure)")


def probe_wazuh() -> Dict[str, Layers]:
    from app.services import wazuh_client as w

    out: Dict[str, Any] = {}
    if not w.credentials_configured():
        out["auth"] = _unknown("credentials_not_configured", "wazuh_api")
        out["application"] = _unknown("needs_authenticated_api", "wazuh_api")
        out["api"] = _unknown("needs_authenticated_api", "wazuh_api")
        return out
    try:
        token = w.authenticate()
    except w.WazuhClientError as exc:
        if exc.status in (401, 403):
            out["api"] = _layer("ok", None, "wazuh_api", "API answered")
            out["auth"] = _layer("unauthorized", "credentials_rejected", "wazuh_api", f"HTTP {exc.status}")
            out["application"] = _unknown("auth_failed", "wazuh_api")
        else:
            out["api"] = _layer("unreachable" if exc.status is None else "degraded", "api_error", "wazuh_api", (str(exc) or "")[:120])
            out["auth"] = _unknown("api_unavailable", "wazuh_api")
            out["application"] = _unknown("api_unavailable", "wazuh_api")
        return out
    version = None
    try:
        version = ((w._request("GET", "/", token=token, timeout=4) or {}).get("data") or {}).get("api_version")
    except w.WazuhClientError:
        pass
    out["api"] = _layer("ok", None, "wazuh_api", f"API {version}" if version else None)
    roles = None
    try:
        me = ((w._request("GET", "/security/users/me", token=token, timeout=4) or {}).get("data") or {})
        item = (me.get("affected_items") or [{}])[0]
        roles = sorted(str(r.get("name")) for r in (item.get("roles") or []) if isinstance(r, dict) and r.get("name"))
    except w.WazuhClientError:
        pass
    out["auth"] = _layer("ok", None, "wazuh_api", f"roles: {', '.join(roles)}" if roles else None)
    try:
        data = w._request("GET", "/manager/status", token=token, timeout=4)
        items = ((data.get("data") or {}).get("affected_items") or [{}])[0]
        stopped = sorted(k for k, v in items.items() if str(v).lower() not in ("running", "disabled"))
        required = wazuh_required_daemons()
        down = [d for d in stopped if d in required]
        idle = [d for d in stopped if d not in required]
        idle_note = f"; not running but optional: {', '.join(idle)}" if idle else ""
        if not items:
            out["application"] = _unknown("empty_status", "wazuh_api")
        elif down:
            out["application"] = _layer("degraded", "core_daemons_not_running", "wazuh_api", ", ".join(down[:8]) + idle_note)
        else:
            running = len(items) - len(stopped)
            out["application"] = _layer("ok", None, "wazuh_api", f"{running} daemons running{idle_note}")
    except w.WazuhClientError as exc:
        out["application"] = _layer("degraded", "status_unavailable", "wazuh_api", (str(exc) or "")[:120])
    out["telemetry"] = _wazuh_agent_telemetry(w, token)
    return out


_WAZUH_CORE_DAEMONS = (
    "wazuh-analysisd",
    "wazuh-remoted",
    "wazuh-db",
    "wazuh-modulesd",
    "wazuh-execd",
    "wazuh-monitord",
    "wazuh-logcollector",
    "wazuh-syscheckd",
    "wazuh-apid",
)


def wazuh_required_daemons() -> Tuple[str, ...]:
    """Daemons whose absence breaks detection. Optional ones (mail, cluster, csyslog...) are off by design on many managers."""
    raw = (os.getenv("TIA_WAZUH_REQUIRED_DAEMONS") or "").strip()
    if raw:
        return tuple(x.strip() for x in raw.split(",") if x.strip())
    return _WAZUH_CORE_DAEMONS


def _wazuh_agent_telemetry(w: Any, token: str) -> Dict[str, Any]:
    """Agent keep-alives are continuous; ingested alert volume is not (a quiet estate raises no alerts)."""
    try:
        data = ((w._request("GET", "/agents/summary/status", token=token, timeout=4) or {}).get("data") or {})
    except w.WazuhClientError:
        return _unknown("agent_summary_unavailable", "wazuh_api")
    conn = data.get("connection") if isinstance(data.get("connection"), dict) else data
    try:
        active = int(conn.get("active") or 0)
        disconnected = int(conn.get("disconnected") or 0)
        never = int(conn.get("never_connected") or 0)
    except (TypeError, ValueError):
        return _unknown("agent_summary_unreadable", "wazuh_api")
    detail = f"{active} agents reporting, {disconnected} disconnected, {never} never connected"
    if active == 0 and disconnected == 0:
        return _unknown("no_agents_enrolled", "wazuh_api") | {"detail": detail}
    if disconnected:
        return _layer("degraded", "agents_disconnected", "wazuh_api", detail)
    return _layer("ok", None, "wazuh_api", detail)


def probe_thehive(base_url: str) -> Dict[str, Layers]:
    from app.services import thehive_client as t

    out: Dict[str, Any] = {}
    try:
        code, body = _http_status(base_url.rstrip("/") + "/api/status")
        version = None
        try:
            import json

            version = ((json.loads(body or "{}").get("versions") or {}).get("TheHive"))
        except ValueError:
            pass
        detail = f"HTTP {code}" + (f", TheHive {version}" if version else "")
        out["api"] = _layer("ok" if code < 500 else "degraded", None if code < 500 else "server_error", "thehive_api", detail)
    except ConnectionError as exc:
        out["api"] = _layer("unreachable", "api_unreachable", "thehive_api", str(exc))
        out["auth"] = _unknown("api_unavailable", "thehive_api")
        out["application"] = _unknown("api_unavailable", "thehive_api")
        return out
    if not t.credentials_configured():
        out["auth"] = _unknown("credentials_not_configured", "thehive_api")
        out["application"] = _unknown("needs_authenticated_api", "thehive_api")
        return out
    try:
        me = t._request("GET", "/api/v1/user/current", timeout=4)
        profile = me.get("profile") if isinstance(me, dict) else None
        org = me.get("organisation") if isinstance(me, dict) else None
        scope = ", ".join(f"{k} {v}" for k, v in (("profile", profile), ("organisation", org)) if v)
        out["auth"] = _layer("ok", None, "thehive_api", scope or None)
        out["application"] = _layer("ok", None, "thehive_api", "authenticated call succeeded")
    except t.TheHiveClientError as exc:
        if exc.status in (401, 403):
            out["auth"] = _layer("unauthorized", "credentials_rejected", "thehive_api", f"HTTP {exc.status}")
            out["application"] = _unknown("auth_failed", "thehive_api")
        else:
            out["auth"] = _unknown("api_error", "thehive_api")
            out["application"] = _layer("degraded", "api_error", "thehive_api", (str(exc) or "")[:120])
    return out


def probe_shuffle(host: str) -> Dict[str, Layers]:
    out: Dict[str, Any] = {}
    try:
        code, body = _http_status(f"http://{host}:3001/api/v1/health")
        ok = code == 200
        out["api"] = _layer("ok" if ok else "degraded", None if ok else "unexpected_status", "shuffle_api", f"HTTP {code}")
        out["application"] = (
            _layer("ok", None, "shuffle_api", "health endpoint ok")
            if ok
            else _layer("degraded", "health_endpoint_not_ok", "shuffle_api", f"HTTP {code}")
        )
    except ConnectionError as exc:
        out["api"] = _layer("unreachable", "api_unreachable", "shuffle_api", str(exc))
        out["application"] = _unknown("api_unavailable", "shuffle_api")
    # The integration is webhook-only: no Shuffle API credential is used, so none can be verified.
    out["auth"] = _unknown("webhook_only_integration", "shuffle")
    return out


def probe_misp() -> Dict[str, Layers]:
    """Use the authorised MISP bridge client. Port-open alone is not application readiness."""
    from app.services import misp_client as m

    out: Dict[str, Any] = {}
    if not m.configured():
        out["api"] = _unknown("credentials_not_configured", "misp_api")
        out["auth"] = _unknown("credentials_not_configured", "misp_api")
        out["application"] = _unknown("needs_api_key", "misp_api")
        return out
    try:
        doc = m.health()
    except Exception as exc:  # noqa: BLE001
        out["api"] = _layer("unreachable", "api_unreachable", "misp_api", type(exc).__name__)
        out["auth"] = _unknown("api_unavailable", "misp_api")
        out["application"] = _unknown("api_unavailable", "misp_api")
        return out
    status = str((doc or {}).get("status") or "").lower()
    if status in ("ok", "healthy", "running"):
        out["api"] = _layer("ok", None, "misp_api", "health endpoint ok")
        out["application"] = _layer("ok", None, "misp_api", "bridge reports healthy")
        out["auth"] = _layer("ok", None, "misp_api", "api key present; health reached")
    elif status in ("unreachable",):
        out["api"] = _layer("unreachable", "api_unreachable", "misp_api", str((doc or {}).get("error") or "")[:120])
        out["auth"] = _unknown("api_unavailable", "misp_api")
        out["application"] = _unknown("api_unavailable", "misp_api")
    else:
        detail = str((doc or {}).get("error") or status or "unexpected")[:120]
        out["api"] = _layer("degraded", "unexpected_status", "misp_api", detail)
        out["auth"] = _unknown("health_degraded", "misp_api")
        out["application"] = _layer("degraded", "health_endpoint_not_ok", "misp_api", detail)
    return out


def probe_velociraptor() -> Dict[str, Layers]:
    """Bridge health only — not proof that hunts are succeeding for every tenant."""
    from app.services import velociraptor_client as v

    out: Dict[str, Any] = {}
    if not v.configured():
        out["api"] = _unknown("credentials_not_configured", "velociraptor_bridge")
        out["auth"] = _unknown("credentials_not_configured", "velociraptor_bridge")
        out["application"] = _unknown("needs_bridge_key", "velociraptor_bridge")
        return out
    try:
        doc = v.health()
    except Exception as exc:  # noqa: BLE001
        out["api"] = _layer("unreachable", "api_unreachable", "velociraptor_bridge", type(exc).__name__)
        out["auth"] = _unknown("api_unavailable", "velociraptor_bridge")
        out["application"] = _unknown("api_unavailable", "velociraptor_bridge")
        return out
    status = str((doc or {}).get("status") or "").lower()
    err = str((doc or {}).get("error") or "")[:120]
    if status in ("ok", "healthy", "running"):
        out["api"] = _layer("ok", None, "velociraptor_bridge", "health endpoint ok")
        out["application"] = _layer("ok", None, "velociraptor_bridge", "bridge reports healthy")
        out["auth"] = _layer("ok", None, "velociraptor_bridge", "bridge key present; health reached")
    elif status == "unreachable":
        out["api"] = _layer("unreachable", "api_unreachable", "velociraptor_bridge", err)
        out["auth"] = _unknown("api_unavailable", "velociraptor_bridge")
        out["application"] = _unknown("api_unavailable", "velociraptor_bridge")
    else:
        out["api"] = _layer("degraded", "unexpected_status", "velociraptor_bridge", err or status)
        out["auth"] = _unknown("health_degraded", "velociraptor_bridge")
        out["application"] = _layer("degraded", "health_endpoint_not_ok", "velociraptor_bridge", err or status)
    return out


def probe_soc_agent() -> Dict[str, Layers]:
    from app.services import soc_agent_client as a

    out: Dict[str, Any] = {}
    if not a.soc_agent_enabled():
        for layer in ("api", "auth", "application"):
            out[layer] = _unknown("soc_agent_disabled", "soc_agent")
        return out
    base = a.soc_agent_url()
    ctx = a.agent_ssl_context()
    try:
        code, body = _http_status(base + "/health", context=ctx)
    except ConnectionError as exc:
        out["api"] = _layer("unreachable", "agent_unreachable_or_tls_failed", "soc_agent", str(exc))
        out["auth"] = _unknown("api_unavailable", "soc_agent")
        out["application"] = _unknown("api_unavailable", "soc_agent")
        return out
    out["api"] = _layer("ok" if code == 200 else "degraded", None if code == 200 else "unexpected_status", "soc_agent", f"HTTP {code}")
    try:
        import json

        doc = json.loads(body or "{}")
        status = str(doc.get("status") or "").lower()
        cursor = ((doc.get("llm") or {}).get("cursor") or {})
        if status == "ok":
            out["application"] = _layer("ok", None, "soc_agent", "model route available")
        else:
            out["application"] = _layer("degraded", "model_route_unavailable", "soc_agent", str(cursor.get("reason") or cursor.get("error") or "")[:120] or None)
    except Exception:  # noqa: BLE001
        out["application"] = _layer("degraded", "health_unreadable", "soc_agent")
    token = a.soc_agent_token()
    if not token:
        out["auth"] = _unknown("credentials_not_configured", "soc_agent")
    else:
        try:
            code, _ = _http_status(base + "/api/cases", headers={"X-Soc-Agent-Token": token}, context=ctx)
            out["auth"] = (
                _layer("ok", None, "soc_agent")
                if code == 200
                else _layer("unauthorized", "credentials_rejected", "soc_agent", f"HTTP {code}")
                if code in (401, 403)
                else _layer("degraded", "unexpected_status", "soc_agent", f"HTTP {code}")
            )
        except ConnectionError as exc:
            out["auth"] = _unknown("api_unavailable", "soc_agent") | {"detail": str(exc)}
    return out


def probe_control_plane() -> Dict[str, Layers]:
    out: Dict[str, Any] = {}
    try:
        from app.db.session import fetch_one

        fetch_one("SELECT 1 AS ok;")
        db = True
    except Exception:  # noqa: BLE001
        db = False
    redis_ok = False
    try:
        from app.services.ai_alert_queue import _redis

        c = _redis()
        redis_ok = bool(c and c.ping())
    except Exception:  # noqa: BLE001
        redis_ok = False
    out["api"] = _layer("ok", None, "in_process")
    if db and redis_ok:
        out["application"] = _layer("ok", None, "in_process", "database and queue answer")
    else:
        bad = [n for n, good in (("database", db), ("redis", redis_ok)) if not good]
        out["application"] = _layer("degraded", "dependency_unavailable", "in_process", ", ".join(bad))
    try:
        from app.services import tia_jobs

        if tia_jobs.schema_ready():
            s = tia_jobs.stats()
            stalled = s.get("oldest_critical_age_s", 0) > 600
            out["telemetry"] = (
                _layer("degraded", "critical_queue_stalled", "tia_jobs", f"oldest critical job waiting {int(s['oldest_critical_age_s'])}s")
                if stalled
                else _layer("ok", None, "tia_jobs", f"{s.get('queued', 0)} queued, {s.get('running', 0)} running, {s.get('dead', 0)} dead")
            )
    except Exception:  # noqa: BLE001
        pass
    return out


def probe_appliances() -> Dict[str, Layers]:
    from app.db.session import fetch_one

    try:
        row = fetch_one(
            "SELECT (SELECT count(*)::int FROM appliances) AS total, "
            "(SELECT count(*)::int FROM appliances WHERE status = 'online') AS online, "
            "(SELECT count(*)::int FROM appliance_heartbeats WHERE heartbeat_at > now() - interval '15 minutes') AS hb;"
        ) or {}
    except Exception as exc:  # noqa: BLE001
        return {"telemetry": _unknown("database_error", "database") | {"detail": type(exc).__name__}}
    total, online, hb = int(row.get("total") or 0), int(row.get("online") or 0), int(row.get("hb") or 0)
    if total == 0:
        return {"telemetry": _unknown("no_appliances_registered", "database")}
    if hb == 0:
        return {"telemetry": _layer("degraded", "no_recent_heartbeats", "database", f"{online}/{total} marked online, 0 heartbeats in 15 min")}
    status = "ok" if online == total else "degraded"
    return {"telemetry": _layer(status, None if status == "ok" else "appliances_not_online", "database", f"{online}/{total} online, {hb} heartbeats in 15 min")}


Layers = Dict[str, Any]  # (typing alias used in annotations above)


# --------------------------------------------------------------------------
# roll-up
# --------------------------------------------------------------------------

def roll_up(layers: Dict[str, Dict[str, Any]], *, reach_required: bool = True) -> Tuple[str, Optional[str]]:
    """Worst verified layer wins. Missing evidence never rolls up to ok."""
    st = {k: (layers.get(k) or {}).get("status", "unknown") for k in LAYERS}
    rs = {k: (layers.get(k) or {}).get("reason") for k in LAYERS}
    if reach_required and st["reachability"] == "unreachable":
        return "unreachable", rs["reachability"] or "connection_failed"
    if st["api"] == "unreachable":
        return "unreachable", rs["api"]
    for k in ("auth", "api", "application", "telemetry"):
        if st[k] == "unauthorized":
            return "unauthorized", rs[k]
    for k in ("application", "api", "telemetry", "reachability"):
        if st[k] == "degraded":
            return "degraded", rs[k]
    verified_beyond_port = [k for k in ("api", "auth", "application", "telemetry") if st[k] == "ok"]
    if not verified_beyond_port:
        return "unknown", "only_port_reachability_verified" if st["reachability"] == "ok" else "no_evidence"
    return "ok", None


# --------------------------------------------------------------------------
# catalogue and assembly
# --------------------------------------------------------------------------

def _specs() -> List[Dict[str, Any]]:
    from app.core.config import get_infra_settings
    from app.services.soc_console_engines import engine_catalog

    infra = get_infra_settings()
    by_id = {e["id"]: e for e in engine_catalog()}
    stale = lambda name, default: int(os.getenv(f"TIA_TELEMETRY_STALE_MINUTES_{name.upper()}", str(default)) or default)  # noqa: E731
    specs: List[Dict[str, Any]] = []

    def spec(eid: str, probe: Optional[Callable[[], Dict[str, Any]]], *, telemetry: bool = True, continuous: bool = False, minutes: int = 240, reach: bool = True) -> None:
        e = by_id.get(eid)
        if not e:
            return
        specs.append(
            {
                "id": eid, "label": e["label"], "host": e["host"], "port": e["port"], "vm": e.get("vm"),
                "probe": probe, "sources": list(e.get("sources") or []) if telemetry else [],
                "continuous": continuous, "minutes": stale(eid, minutes), "reach": reach,
            }
        )

    spec("control_plane", probe_control_plane, telemetry=False, reach=False)
    spec("wazuh", probe_wazuh, minutes=60)
    spec("thehive", lambda: probe_thehive(infra.thehive_url), telemetry=False)
    spec("shuffle", lambda: probe_shuffle(infra.shuffle_host), telemetry=False)
    spec("suricata", None, minutes=1440)
    # Zeek has no direct control-plane API; ingest freshness is the application signal.
    spec("zeek", None, minutes=1440)
    spec("misp", probe_misp, telemetry=False)
    spec("greenbone", None, minutes=10080)
    spec("velociraptor", probe_velociraptor, telemetry=False)
    spec("secure_edge", None, minutes=1440)
    spec("soc_agent", probe_soc_agent, telemetry=False)
    spec("appliances", probe_appliances, telemetry=False, reach=False)
    return specs


def check_engine(spec: Dict[str, Any]) -> Dict[str, Any]:
    layers: Dict[str, Dict[str, Any]] = {}
    started = time.monotonic()
    if spec["reach"]:
        layers["reachability"] = probe_reachability(spec["host"], spec["port"])
    else:
        layers["reachability"] = _layer("ok", None, "not_applicable", "in-process or database-derived")
    reachable = layers["reachability"]["status"] == "ok"
    if spec["probe"]:
        if reachable or not spec["reach"]:
            try:
                layers.update(spec["probe"]())
            except Exception as exc:  # noqa: BLE001
                logger.warning("engine probe %s failed: %s", spec["id"], type(exc).__name__)
                # The adapter itself failed: that is a fault to show, not a gap to ignore.
                layers.setdefault("api", _layer("degraded", "health_probe_failed", spec["id"], type(exc).__name__))
                for k in ("auth", "application"):
                    layers.setdefault(k, _unknown("health_probe_failed", spec["id"]))
        else:
            for k in ("api", "auth", "application"):
                layers[k] = _unknown("host_unreachable", spec["id"])
    else:
        for k in ("api", "auth", "application"):
            layers[k] = _unknown("no_adapter", spec["id"])
    if "telemetry" not in layers:
        layers["telemetry"] = (
            probe_telemetry(spec["sources"], expect_continuous=spec["continuous"], stale_minutes=spec["minutes"])
            if spec["sources"]
            else _unknown("no_telemetry_source", spec["id"])
        )
    status, reason = roll_up(layers, reach_required=spec["reach"])
    return {
        "engine": spec["id"],
        "label": spec["label"],
        "vm": spec.get("vm"),
        "host": spec["host"],
        "port": spec["port"],
        "status": status,
        "reason": reason,
        "layers": {k: layers.get(k) or _unknown("not_checked") for k in LAYERS},
        "verified_layers": [k for k in LAYERS if (layers.get(k) or {}).get("status") == "ok"],
        "unverified_layers": [k for k in LAYERS if (layers.get(k) or {}).get("status") == "unknown"],
        "scope": "platform",
        "checked_at": _now_iso(),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def _label_cache(entry: Dict[str, Any], stored_at: float, *, served_from_cache: bool, note: Optional[str] = None) -> Dict[str, Any]:
    age = int(time.monotonic() - stored_at)
    out = dict(entry)
    out["cached"] = served_from_cache
    out["age_s"] = age if served_from_cache else 0
    out["freshness"] = "cached" if served_from_cache else "live"
    if note:
        out["note"] = note
    return out


def get_health(*, force: bool = False, only: Optional[str] = None) -> Dict[str, Any]:
    """All engines (or one), each labelled live or cached. Never blocks past the deadline."""
    specs = [s for s in _specs() if not only or s["id"] == only]
    now = time.monotonic()
    results: Dict[str, Dict[str, Any]] = {}
    pending: List[Dict[str, Any]] = []
    for s in specs:
        with _lock:
            hit = _cache.get(s["id"])
        if hit and not force and now - hit[0] < _ttl():
            results[s["id"]] = _label_cache(hit[1], hit[0], served_from_cache=True)
        else:
            pending.append(s)
    futures = {_executor.submit(check_engine, s): s for s in pending}
    done, not_done = wait(list(futures), timeout=_deadline())
    for fut in done:
        s = futures[fut]
        try:
            entry = fut.result()
            with _lock:
                _cache[s["id"]] = (time.monotonic(), entry)
            results[s["id"]] = _label_cache(entry, time.monotonic(), served_from_cache=False)
        except Exception as exc:  # noqa: BLE001
            results[s["id"]] = _failed_entry(s, "probe_error", type(exc).__name__)
    for fut in not_done:
        s = futures[fut]
        with _lock:
            hit = _cache.get(s["id"])
        if hit:
            results[s["id"]] = _label_cache(hit[1], hit[0], served_from_cache=True, note="live check timed out; showing the last result")
        else:
            results[s["id"]] = _failed_entry(s, "check_timed_out", f"no answer within {_deadline():.0f}s")
    engines = [results[s["id"]] for s in specs if s["id"] in results]
    counts: Dict[str, int] = {}
    for e in engines:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    return {"scope": "platform", "checked_at": _now_iso(), "engines": engines, "counts": counts, "total": len(engines)}


def _failed_entry(spec: Dict[str, Any], reason: str, detail: str) -> Dict[str, Any]:
    layers = {k: _unknown(reason, spec["id"]) for k in LAYERS}
    return {
        "engine": spec["id"], "label": spec["label"], "vm": spec.get("vm"), "host": spec["host"], "port": spec["port"],
        "status": "unknown", "reason": reason, "layers": layers, "verified_layers": [], "unverified_layers": list(LAYERS),
        "scope": "platform", "checked_at": _now_iso(), "duration_ms": None, "cached": False, "age_s": 0, "freshness": "live", "note": detail,
    }


def clear_cache() -> None:
    with _lock:
        _cache.clear()


# --------------------------------------------------------------------------
# role-aware view and spoken summary
# --------------------------------------------------------------------------

def redact_for_role(report: Dict[str, Any], role: str) -> Dict[str, Any]:
    """Platform-wide infrastructure detail (hosts, ports, error text) is for privileged roles only."""
    if role in PRIVILEGED_ROLES:
        return report
    out = dict(report)
    engines = []
    for e in report["engines"]:
        c = {k: v for k, v in e.items() if k not in ("host", "port", "vm")}
        c["layers"] = {k: {kk: vv for kk, vv in v.items() if kk != "detail"} for k, v in e["layers"].items()}
        engines.append(c)
    out["engines"] = engines
    out["detail_level"] = "status_only"
    return out


_REASON_TEXT = {
    "connection_failed": "is not answering",
    "api_unreachable": "its API is not answering",
    "agent_unreachable_or_tls_failed": "is not answering (or its certificate failed verification)",
    "credentials_rejected": "rejected our credentials",
    "telemetry_stale": "has stopped sending recent events",
    "core_daemons_not_running": "has core daemons that are not running",
    "agents_disconnected": "has agents that stopped reporting",
    "model_route_unavailable": "cannot reach its model",
    "dependency_unavailable": "has an unavailable dependency",
    "critical_queue_stalled": "has a critical investigation waiting too long",
    "check_timed_out": "did not answer the health check in time",
    "only_port_reachability_verified": "has an open port, but I have no way to verify more than that",
    "soc_agent_disabled": "is switched off",
    "no_recent_heartbeats": "has no recent appliance heartbeats",
    "appliances_not_online": "has appliances that are not online",
}
_STATUS_WORD = {"ok": "healthy", "degraded": "degraded", "unreachable": "unreachable", "unauthorized": "rejecting our login", "unknown": "unverified"}


def summarize(report: Dict[str, Any], *, focus: Optional[str] = None) -> Dict[str, str]:
    engines = report["engines"]
    if focus:
        engines = [e for e in engines if e["engine"] == focus] or engines
    cached = [e for e in engines if e.get("cached")]
    age = max((e.get("age_s", 0) for e in cached), default=0)
    fresh_note = f" Some results are {age} seconds old." if cached else " Checked just now."
    problems = [e for e in engines if e["status"] != "ok"]
    healthy = [e for e in engines if e["status"] == "ok"]
    if focus and len(engines) == 1:
        e = engines[0]
        verified = ", ".join(v.replace("_", " ") for v in e["verified_layers"]) or "nothing beyond the host"
        unv = ", ".join(v.replace("_", " ") for v in e["unverified_layers"])
        reason = _REASON_TEXT.get(e.get("reason") or "", (e.get("reason") or "").replace("_", " "))
        line = f"{e['label']} is {_STATUS_WORD[e['status']]}" + (f": it {reason}." if reason and e["status"] != "ok" else ".")
        line += f" Verified: {verified}." + (f" Not verified: {unv}." if unv else "")
        return {"answer": line + fresh_note, "spoken": f"{e['label']} is {_STATUS_WORD[e['status']]}." + (f" It {reason}." if reason and e["status"] != "ok" else "")}
    if not problems:
        msg = f"All {len(healthy)} engines I can check are healthy."
        return {"answer": msg + fresh_note, "spoken": msg}
    parts = []
    for e in problems[:6]:
        reason = _REASON_TEXT.get(e.get("reason") or "", (e.get("reason") or "").replace("_", " "))
        parts.append(f"{e['label']} is {_STATUS_WORD[e['status']]}" + (f" ({reason})" if reason else ""))
    more = f", and {len(problems) - 6} more" if len(problems) > 6 else ""
    msg = f"{len(healthy)} of {len(engines)} engines are verified healthy. " + "; ".join(parts) + more + "."
    spoken = f"{len(problems)} of {len(engines)} engines need attention: " + "; ".join(p.split(" (")[0] for p in parts[:3]) + ("." if len(problems) <= 3 else " and others.")
    return {"answer": msg + fresh_note, "spoken": spoken}
