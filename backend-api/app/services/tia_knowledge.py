"""Verified MSSP knowledge for TIA: inventory, dependencies, ingest vs reachability.

Every answer this module builds is labelled as one of:

  observed     a live API, probe, database row or hypervisor query
  documented   the checked-in topology / role catalogue (may lag the live estate)
  hypothesis   a possible reading, not a finding
  unknown      not checked, not authorised, or the source did not answer

Retrieved documents, logs and web content are evidence. They never grant a
permission or invent a tool. A critical detection *label* is not a critical incident.
"""

from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.db.session import fetch_all, fetch_one
from app.services.tia_tools import Scope, ToolError, authorize, get_alert_row

logger = logging.getLogger(__name__)

# Documented topology. Live Proxmox/health may disagree; the conflict is reported, not papered over.
COMPONENTS: Dict[str, Dict[str, Any]] = {
    "control_plane": {
        "aliases": ("control plane", "mssp-control", "api", "postgres", "backend"),
        "vmid": 100, "vm_name": "mssp-control", "engine_id": "control_plane",
        "role": "Control plane (FastAPI, Postgres, Redis, Admin/Customer/SOC portals)",
        "depends_on": (),
        "dependents": ("wazuh ingest adapter", "thehive adapter", "soc_agent callbacks", "admin portal", "customer portal", "soc console"),
        "design": "VM 100. Portals Admin :3000, Customer :3001, SOC :3443 proxy the API. Engines are adapters, not customer UIs.",
    },
    "wazuh": {
        "aliases": ("wazuh", "wazuh manager", "wazuh-stack", "siem"),
        "vmid": 101, "vm_name": "wazuh-stack", "engine_id": "wazuh",
        "role": "Wazuh Manager, Indexer and Dashboard",
        "depends_on": (),
        "dependents": ("suricata", "zeek", "endpoint agents", "control_plane ingest"),
        "design": "VM 101. Agents and Suricata/Zeek forward here. Control plane normalises alerts into PostgreSQL.",
    },
    "thehive": {
        "aliases": ("thehive", "the hive", "cases", "case manager"),
        "vmid": 102, "vm_name": "thehive-shuffle", "engine_id": "thehive",
        "role": "TheHive case management",
        "depends_on": (),
        "dependents": ("shuffle", "control_plane case adapter"),
        "design": "Co-located with Shuffle on VM 102. Shared org default is MSSP.",
    },
    "shuffle": {
        "aliases": ("shuffle", "soar", "playbooks"),
        "vmid": 102, "vm_name": "thehive-shuffle", "engine_id": "shuffle",
        "role": "Shuffle SOAR (webhook integration)",
        "depends_on": ("thehive",),
        "dependents": ("control_plane webhooks",),
        "design": "VM 102 with TheHive. Auth to Shuffle is webhook-only; there is no verified API login.",
    },
    "suricata": {
        "aliases": ("suricata", "ids", "nids"),
        "vmid": 106, "vm_name": "suricata-sensor", "engine_id": "suricata",
        "role": "Suricata IDS",
        "depends_on": ("wazuh",),
        "dependents": ("control_plane ingest",),
        "design": "VM 106. Wazuh agent tails eve.json to Manager 101.",
    },
    "zeek": {
        "aliases": ("zeek", "bro"),
        "vmid": 106, "vm_name": "suricata-sensor", "engine_id": "zeek",
        "role": "Zeek network telemetry",
        "depends_on": ("wazuh",),
        "dependents": ("control_plane ingest",),
        "design": "Co-located with Suricata on VM 106; notices forward through Wazuh.",
    },
    "misp": {
        "aliases": ("misp", "threat intel"),
        "vmid": 108, "vm_name": "misp", "engine_id": "misp",
        "role": "MISP-compatible threat-intel bridge",
        "depends_on": (),
        "dependents": ("control_plane intel adapter",),
        "design": "VM 108. Bridge, not a full upstream MISP UI.",
    },
    "greenbone": {
        "aliases": ("greenbone", "openvas", "nuclei", "vuls", "vuln scanner"),
        "vmid": 109, "vm_name": "greenbone", "engine_id": "greenbone",
        "role": "Greenbone CE with Nuclei + Vuls",
        "depends_on": (),
        "dependents": ("control_plane vuln adapter",),
        "design": "VM 109. Scanners never run on the control plane.",
    },
    "velociraptor": {
        "aliases": ("velociraptor", "dfir"),
        "vmid": 110, "vm_name": "velociraptor", "engine_id": "velociraptor",
        "role": "Velociraptor DFIR",
        "depends_on": (),
        "dependents": ("control_plane DFIR adapter",),
        "design": "VM 110.",
    },
    "automation": {
        "aliases": ("ansible", "automation", "vm 112"),
        "vmid": 112, "vm_name": "automation", "engine_id": None,
        "role": "Ansible automation controller",
        "depends_on": (),
        "dependents": ("engine installs",),
        "design": "VM 112. Live engine installs run from here, not from VM 100.",
    },
    "soc_agent": {
        "aliases": ("soc agent", "tia brain", "cursor agent", "vm 117"),
        "vmid": 117, "vm_name": "mssp-soc-agent", "engine_id": "soc_agent",
        "role": "SOC agent (TIA model route)",
        "depends_on": ("control_plane",),
        "dependents": ("deep investigation jobs",),
        "design": "VM 117. Cursor CLI is a development/subscription interface, not a cleared production inference path.",
    },
    "admin_portal": {
        "aliases": ("admin portal", "admin ui", "port 3000", ":3000"),
        "vmid": 100, "vm_name": "mssp-control", "engine_id": None,
        "role": "Admin/SOC portal (nginx)",
        "depends_on": ("control_plane",),
        "dependents": (),
        "design": "Same VM as the API. Staff roles only.",
    },
    "customer_portal": {
        "aliases": ("customer portal", "customer ui", "port 3001", ":3001"),
        "vmid": 100, "vm_name": "mssp-control", "engine_id": None,
        "role": "Customer portal (nginx)",
        "depends_on": ("control_plane",),
        "dependents": (),
        "design": "Same VM as the API. Customer roles only; never calls /admin.",
    },
    "soc_console": {
        "aliases": ("soc console", "soc ui", "port 3443", ":3443", "tia console"),
        "vmid": 100, "vm_name": "mssp-control", "engine_id": None,
        "role": "SOC Agent Console (HTTPS for microphone)",
        "depends_on": ("control_plane",),
        "dependents": (),
        "design": "frontend-soc on VM 100, HTTPS :3443.",
    },
}


def resolve_component(text: str, *, source_tool: Optional[str] = None) -> Optional[str]:
    """Best component id from operator wording or the open alert's source. None if unnamed."""
    low = f" {(text or '').lower()} "
    scored: List[Tuple[int, str]] = []
    for cid, spec in COMPONENTS.items():
        for alias in spec["aliases"]:
            needle = f" {alias} "
            if needle in low or low.strip() == alias:
                scored.append((len(alias), cid))
                break
    if scored:
        scored.sort(reverse=True)
        return scored[0][1]
    if source_tool:
        st = str(source_tool).lower()
        if st in COMPONENTS:
            return st
        for cid, spec in COMPONENTS.items():
            if st in spec["aliases"]:
                return cid
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def format_report(title: str, observed: List[str], documented: List[str], hypotheses: List[str], unknowns: List[str], *, spoken: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    lines = [title]
    if observed:
        lines.append("Observed:")
        lines.extend(f"- {x}" for x in observed)
    if documented:
        lines.append("Documented design:")
        lines.extend(f"- {x}" for x in documented)
    if hypotheses:
        lines.append("Hypothesis (not a finding):")
        lines.extend(f"- {x}" for x in hypotheses)
    if unknowns:
        lines.append("Not verified / not checked:")
        lines.extend(f"- {x}" for x in unknowns)
    out = {
        "answer": "\n".join(lines),
        "spoken_answer": spoken,
        "observed": observed,
        "documented": documented,
        "hypotheses": hypotheses,
        "unknowns": unknowns,
        "checked_at": _now(),
    }
    if extra:
        out.update(extra)
    return out


def _live_proxmox() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        from app.services.soc_console_proxmox import gather_proxmox_inventory, proxmox_enabled

        if not proxmox_enabled():
            return None, "proxmox_probe_disabled_or_key_missing"
        inv = gather_proxmox_inventory(force=False, allow_stale=True)
        if inv.get("error"):
            return inv, str(inv.get("error"))[:160]
        return inv, None
    except Exception as exc:  # noqa: BLE001
        logger.warning("proxmox inventory unavailable: %s", type(exc).__name__)
        return None, type(exc).__name__


def _vm_live_row(inv: Optional[Dict[str, Any]], vmid: int) -> Optional[Dict[str, Any]]:
    if not inv:
        return None
    for v in inv.get("vms") or []:
        try:
            if int(v.get("vmid") or 0) == vmid:
                return v
        except (TypeError, ValueError):
            continue
    named = inv.get("named") or {}
    for row in named.values() if isinstance(named, dict) else []:
        if isinstance(row, dict) and int(row.get("vmid") or 0) == vmid:
            return row
    return None


def platform_inventory(scope: Scope) -> Dict[str, Any]:
    authorize("platform_inventory", scope)
    inv, err = _live_proxmox()
    observed: List[str] = []
    documented: List[str] = []
    unknowns: List[str] = []
    rows: List[Dict[str, Any]] = []
    if inv and not err:
        src = inv.get("source") or "proxmox"
        observed.append(f"Hypervisor inventory via {src} at {inv.get('checked_at') or 'unknown time'}.")
    elif err:
        unknowns.append(f"Live Proxmox was not available ({err}). VM running-state is unverified.")
    for cid, spec in COMPONENTS.items():
        live = _vm_live_row(inv, int(spec["vmid"]))
        status = None
        if live:
            status = live.get("status")
            observed.append(
                f"VM {spec['vmid']} ({live.get('name') or spec['vm_name']}) is {status}"
                + (f", {live.get('cpus')} vCPU, {live.get('mem_max_gb')} GB RAM" if live.get("mem_max_gb") is not None else "")
                + f" — {spec['role']}."
            )
        else:
            documented.append(f"VM {spec['vmid']} {spec['vm_name']}: {spec['role']}.")
        rows.append({"id": cid, **{k: spec[k] for k in ("vmid", "vm_name", "role")}, "live_status": status})
    spoken = (
        f"I have {len(COMPONENTS)} documented components. "
        + ("Live VM status is included." if inv and not err else "Live VM status could not be checked.")
    )
    return format_report(
        "Platform inventory (documented catalogue plus live hypervisor where reachable).",
        observed, documented, [], unknowns, spoken=spoken, extra={"components": rows, "proxmox_error": err},
    )


def component_lookup(scope: Scope, component_id: str) -> Dict[str, Any]:
    authorize("component_lookup", scope)
    spec = COMPONENTS.get(component_id)
    if not spec:
        raise ToolError("not_found", "I don't have that component in the verified catalogue.")
    inv, err = _live_proxmox()
    live = _vm_live_row(inv, int(spec["vmid"]))
    observed: List[str] = []
    documented = [
        f"{spec['role']} is documented on VM {spec['vmid']} ({spec['vm_name']}).",
        spec["design"],
    ]
    if spec["depends_on"]:
        documented.append("Depends on: " + ", ".join(spec["depends_on"]) + ".")
    if spec["dependents"]:
        documented.append("Other pieces that use it: " + ", ".join(spec["dependents"]) + ".")
    unknowns: List[str] = []
    if live:
        observed.append(
            f"Proxmox reports VM {spec['vmid']} ({live.get('name')}) {live.get('status')}"
            + (f", CPU {live.get('cpu_pct')}%" if live.get("cpu_pct") is not None else "")
            + (f", RAM {live.get('mem_used_gb')}/{live.get('mem_max_gb')} GB" if live.get("mem_max_gb") is not None else "")
            + f" (source {inv.get('source') if inv else 'proxmox'})."
        )
    elif err:
        unknowns.append(f"Could not query Proxmox ({err}), so running-state is unverified.")
    else:
        unknowns.append(f"VM {spec['vmid']} was not in the live hypervisor list.")
    engine_id = spec.get("engine_id")
    health = None
    if engine_id:
        try:
            from app.services import tia_tools as tools

            report = tools.engine_health(scope, engine=engine_id)
            engines = report.get("engines") or []
            health = engines[0] if engines else None
            if health:
                layers = health.get("layers") or {}
                observed.append(
                    f"Health roll-up {health.get('status')} at {health.get('checked_at')} "
                    f"(reachability { (layers.get('reachability') or {}).get('status') }, "
                    f"API { (layers.get('api') or {}).get('status') }, "
                    f"auth { (layers.get('auth') or {}).get('status') }, "
                    f"application { (layers.get('application') or {}).get('status') }, "
                    f"telemetry { (layers.get('telemetry') or {}).get('status') })."
                )
                if health.get("cached"):
                    observed.append(f"That health result is cached ({health.get('age_s')}s old).")
        except ToolError as exc:
            unknowns.append(f"Engine health: {exc.message}")
        except Exception as exc:  # noqa: BLE001
            unknowns.append(f"Engine health could not run ({type(exc).__name__}).")
    spoken = f"{spec['role']} is on VM {spec['vmid']}."
    if live:
        spoken += f" Proxmox shows it {live.get('status')}."
    if spec["dependents"]:
        spoken += " Things that use it: " + ", ".join(list(spec["dependents"])[:3]) + "."
    return format_report(
        f"{spec['role']}.",
        observed, documented, [], unknowns, spoken=spoken,
        extra={"component": component_id, "vmid": spec["vmid"], "health": health, "live": live},
    )


def ingest_status(scope: Scope, engine_id: str = "wazuh") -> Dict[str, Any]:
    """Reachable is not the same as authenticated, processing, or ingesting events."""
    authorize("ingest_status", scope)
    from app.services import tia_tools as tools

    report = tools.engine_health(scope, engine=engine_id)
    engines = [e for e in (report.get("engines") or []) if e.get("engine") == engine_id] or (report.get("engines") or [])
    if not engines:
        raise ToolError("not_found", "I have no health record for that engine.")
    e = engines[0]
    layers = e.get("layers") or {}
    observed: List[str] = []
    hypotheses: List[str] = []
    unknowns: List[str] = []

    def layer(name: str) -> Dict[str, Any]:
        return layers.get(name) or {}

    for name in ("reachability", "api", "auth", "application", "telemetry"):
        ly = layer(name)
        st = ly.get("status") or "unknown"
        detail = ly.get("detail") or ly.get("reason") or ""
        src = ly.get("source") or ""
        age = ""
        if e.get("cached"):
            age = f", cached {e.get('age_s')}s"
        line = f"{name}: {st}" + (f" ({detail})" if detail else "") + (f" via {src}" if src else "") + age
        if st == "unknown":
            unknowns.append(line)
        else:
            observed.append(line)

    row = fetch_one(
        "SELECT extract(epoch FROM (now() - max(created_at)))::bigint AS age_s, count(*)::bigint AS n, "
        "max(created_at AT TIME ZONE 'utc')::text AS last_at "
        "FROM security_alerts WHERE lower(coalesce(source_tool,'')) = %s;",
        (engine_id,),
    ) or {}
    if row.get("last_at"):
        observed.append(
            f"Control-plane ingest: last {engine_id} alert stored {row['last_at']} UTC "
            f"({row.get('age_s')}s ago, {row.get('n')} total rows). Source: security_alerts."
        )
    else:
        unknowns.append(f"Control-plane ingest: no {engine_id} rows in security_alerts.")

    reach_ok = layer("reachability").get("status") == "ok"
    auth_ok = layer("auth").get("status") == "ok"
    app_ok = layer("application").get("status") == "ok"
    tel = layer("telemetry").get("status")
    if reach_ok and tel in ("degraded", "unknown") and row.get("age_s") and int(row["age_s"]) > 3600:
        hypotheses.append(
            "The service answers on the network, but stored events are old. That can be a quiet estate, a broken forwarder, or a stalled ingest — I have not distinguished those."
        )
    if reach_ok and not auth_ok:
        unknowns.append("Reachable does not mean our credentials work; auth is not ok.")
    if reach_ok and auth_ok and not app_ok:
        unknowns.append("Login succeeded but the application layer is not verified healthy.")

    conflicts: List[str] = []
    if reach_ok and tel == "degraded":
        conflicts.append("Reachability is ok while telemetry is degraded.")
    spoken = (
        f"{e.get('label') or engine_id} reachability is {layer('reachability').get('status')}. "
        f"Event ingest is {tel or 'unverified'}."
    )
    extra = {
        "engine": engine_id,
        "layers": {k: layer(k).get("status") for k in ("reachability", "api", "auth", "application", "telemetry")},
        "conflicts": conflicts,
        "last_ingest_age_s": row.get("age_s"),
        "freshness": e.get("freshness"),
    }
    title = f"{e.get('label') or engine_id}: reachable is not the same as events arriving."
    if conflicts:
        observed.append("Conflict: " + " ".join(conflicts))
    return format_report(title, observed, [], hypotheses, unknowns, spoken=spoken, extra=extra)


def customers_overview(scope: Scope) -> Dict[str, Any]:
    authorize("customers_overview", scope)
    clause, params = (" AND t.id = %s::uuid", (scope.tenant_id,)) if scope.tenant_id else ("", ())
    rows = fetch_all(
        f"""
        SELECT t.short_code, t.name,
               (SELECT count(*) FROM security_alerts sa
                 WHERE sa.tenant_id = t.id AND sa.status NOT IN ('closed','false_positive')
                   AND lower(sa.severity)='critical')::int AS critical_open,
               (SELECT count(*) FROM security_alerts sa
                 WHERE sa.tenant_id = t.id AND sa.status NOT IN ('closed','false_positive')
                   AND lower(sa.severity)='high')::int AS high_open,
               (SELECT count(*) FROM incidents i
                 WHERE i.tenant_id = t.id AND i.status NOT IN ('closed','resolved'))::int AS incidents_open
        FROM tenants t
        WHERE true{clause}
        ORDER BY 3 DESC, 4 DESC, t.short_code
        LIMIT 25;
        """,
        params,
    )
    observed = [
        f"{r['short_code']}: {r['critical_open']} critical, {r['high_open']} high, {r['incidents_open']} open incidents"
        for r in rows
    ] or ["No tenants in this scope."]
    spoken = (
        f"{len(rows)} customer{'s' if len(rows) != 1 else ''} in scope. "
        + (f"Most urgent is {rows[0]['short_code']}." if rows else "")
    )
    return format_report(
        "Customers in the current conversation scope (live database counts).",
        observed, [], [], [], spoken=spoken, extra={"tenants": rows},
    )


def portal_status(scope: Scope) -> Dict[str, Any]:
    authorize("portal_status", scope)
    targets = (
        ("admin_portal", os.getenv("TIA_ADMIN_HEALTH_URL", "http://frontend-admin/"), "Admin :3000"),
        ("customer_portal", os.getenv("TIA_CUSTOMER_HEALTH_URL", "http://frontend-customer/"), "Customer :3001"),
        ("soc_console", os.getenv("TIA_SOC_HEALTH_URL", "http://frontend-soc/"), "SOC console"),
        ("control_plane", os.getenv("TIA_API_HEALTH_URL", "http://127.0.0.1:8000/health"), "API /health"),
    )
    observed: List[str] = []
    unknowns: List[str] = []
    documented = [
        "Admin :3000, Customer :3001 and SOC :3443 are nginx frontends on VM 100 in front of the API.",
        "HTTP 200 on the home page is reachability of the UI, not proof the API or engines are processing correctly.",
    ]
    for _cid, url, label in targets:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                code = resp.status
            observed.append(f"{label}: HTTP {code} from {url} (reachability only).")
        except urllib.error.HTTPError as exc:
            observed.append(f"{label}: HTTP {exc.code} from {url}.")
        except Exception as exc:  # noqa: BLE001
            unknowns.append(f"{label}: not checked ({type(exc).__name__} talking to {url}).")
    spoken = "Portals: I checked UI reachability, not full processing."
    return format_report("Portals and API reachability.", observed, documented, [], unknowns, spoken=spoken)


def assess_criticality(scope: Scope, alert_id: str) -> Dict[str, Any]:
    """A critical *rule label* is not proof of a critical incident."""
    authorize("assess_criticality", scope)
    from app.services import tia_tools as tools

    ev = tools.explain_evidence(scope, alert_id)
    a = ev["alert"]
    observed = [
        f"Stored severity is {a['severity']} for {a['title']} ({a['short_code']}), source {a.get('source_tool') or 'unknown'}.",
    ]
    if ev.get("description"):
        observed.append(f"Detection text: {ev['description'][:240]}")
    observed.extend(f"{p['field']}: {p['value']}" for p in ev.get("present") or [])
    documented = [
        "Severity in this platform is copied from the detection engine. A critical rule label is not, by itself, a confirmed critical incident.",
        "Closing, isolating or treating this as a false positive still needs an analyst or a verified playbook.",
    ]
    hypotheses: List[str] = []
    desc = (ev.get("description") or "").lower() + " " + (a.get("title") or "").lower()
    if "temp" in desc or "staging" in desc or "administrator" in desc:
        hypotheses.append(
            "This could be expected administrator or installer activity landing in a common staging path. That is a hypothesis until process, parent, hash or identity evidence says otherwise."
        )
    else:
        hypotheses.append(
            "It could be malicious staging, or it could be authorised software behaviour that matched a noisy rule. The record does not decide that."
        )
    unknowns = []
    if ev.get("missing"):
        unknowns.append("Not in the record: " + ", ".join(ev["missing"]) + ".")
    inv = ev.get("investigation") or {}
    res = inv.get("latest_result")
    if res:
        observed.append(
            f"Last investigation execution_status={res.get('execution_status')}, verdict={res.get('verdict')}, "
            f"disposition={res.get('disposition')} (model views are unverified)."
        )
        if str(res.get("verdict") or "").upper().startswith("BENIGN"):
            unknowns.append("A model 'benign' view is not a false-positive finding.")
    else:
        unknowns.append("No completed TIA investigation on this alert.")
    ai = ev.get("prior_ai_assessment") or {}
    if ai.get("verdict"):
        observed.append(f"Earlier automated assessment: {ai.get('verdict')} (recommendation, not a finding).")
    spoken = (
        f"It is labelled {a['severity']} because the detection engine scored it that way. "
        "That label is not proof of a critical incident."
    )
    return format_report(
        f"Why {a['short_code']} is labelled {a['severity']}.",
        observed, documented, hypotheses, unknowns, spoken=spoken,
        extra={"alert_id": a["id"], "severity": a["severity"]},
    )


def investigation_delay(scope: Scope, alert_id: str) -> Dict[str, Any]:
    authorize("investigation_delay", scope)
    from app.services import tia_jobs
    from app.services import tia_tools as tools

    row = get_alert_row(scope, alert_id)
    if not row:
        raise ToolError("not_found", "I can't find that alert in this scope.")
    job = tia_jobs.latest_for_alert(row["id"])
    inv = tools.describe_alert(scope, row["id"])["investigation"]
    observed: List[str] = []
    documented = [
        "Deep investigation is a durable job. Voice turns must not wait for the model. Background workers are independent of this session.",
    ]
    hypotheses: List[str] = []
    unknowns: List[str] = []
    if not job:
        observed.append("No investigation job is queued for this alert.")
        hypotheses.append("It is delayed because it was never queued, not because the model is slow.")
    else:
        observed.append(
            f"Job {job['id'][:8]} is {job['state']} (attempt {job['attempts']} of {job['max_attempts']}, source {job.get('source')})."
        )
        if job.get("last_error_category"):
            observed.append(f"Last error category: {job['last_error_category']}.")
        if job["state"] == "queued":
            hypotheses.append("The worker has not claimed it yet, or it is waiting on backoff.")
        elif job["state"] == "running":
            hypotheses.append("A worker holds the lease; the model route on the SOC agent may still be in flight.")
        elif job["state"] == "dead":
            hypotheses.append("It exhausted attempts and is in the dead-letter path; that needs an analyst, not another voice retry.")
    item = inv.get("review_item")
    if item:
        observed.append(
            f"Review item {item.get('assessed_priority')} status {item.get('status')}, due {item.get('due_at')}, "
            f"{'assigned to ' + item['assigned_to'] if item.get('assigned_to') else 'unassigned'}."
        )
    try:
        from app.services import tia_schema

        ready = tia_schema.readiness() or {}
        for fault in (ready.get("faults") or [])[:6]:
            if isinstance(fault, dict):
                observed.append(f"Readiness {fault.get('code')}: {str(fault.get('message') or '')[:160]}")
            elif fault:
                observed.append(str(fault)[:160])
        backlog = ready.get("backlog") or {}
        if backlog.get("review_overdue"):
            observed.append(f"{backlog['review_overdue']} review item(s) overdue on the platform.")
        if backlog.get("stale_attempts"):
            observed.append(f"{backlog['stale_attempts']} investigation attempt(s) have had no result for over 10 minutes.")
    except Exception as exc:  # noqa: BLE001
        unknowns.append(f"Readiness report unavailable ({type(exc).__name__}).")
    try:
        from app.services import tia_tools as ttools

        agent = ttools.engine_health(scope, engine="soc_agent")
        eng = (agent.get("engines") or [{}])[0]
        observed.append(f"SOC agent health roll-up: {eng.get('status')} (application {(eng.get('layers') or {}).get('application', {}).get('status')}).")
        if eng.get("status") not in ("ok", None):
            hypotheses.append("If the SOC agent cannot reach its model, jobs sit until the lease expires and retry.")
    except Exception as exc:  # noqa: BLE001
        unknowns.append(f"SOC agent health not checked ({type(exc).__name__}).")
    spoken = "I checked the job, the review queue and the SOC agent. " + (
        f"The job is {job['state']}." if job else "There is no job queued."
    )
    return format_report(
        f"Why investigation for {row['short_code']} may be delayed.",
        observed, documented, hypotheses, unknowns, spoken=spoken, extra={"job": job, "alert_id": row["id"]},
    )


def known_unknowns(scope: Scope, alert_id: str) -> Dict[str, Any]:
    authorize("known_unknowns", scope)
    from app.services import tia_tools as tools

    ev = tools.explain_evidence(scope, alert_id)
    a = ev["alert"]
    observed = [f"{p['field']}: {p['value']}" for p in ev.get("present") or []]
    if ev.get("description"):
        observed.insert(0, f"Detection: {ev['description'][:240]}")
    unknowns = []
    if ev.get("missing"):
        unknowns.append("Record gaps: " + ", ".join(ev["missing"]) + ".")
    inv = ev.get("investigation") or {}
    checked = (inv.get("checked") or {}).get("sections") or {}
    for name, sec in checked.items():
        st = sec.get("status")
        if st == "present":
            observed.append(f"Checked {name}: {sec.get('items')} item(s).")
        elif st == "empty":
            observed.append(f"Checked {name}: nothing found ({sec.get('note') or 'empty'}).")
        else:
            unknowns.append(f"{name}: {st}" + (f" ({sec.get('note')})" if sec.get("note") else "") + ".")
    if not checked:
        unknowns.append("No investigation evidence manifest is recorded, so I can only speak to the stored alert row.")
    view = inv.get("model_view") or {}
    hypotheses: List[str] = []
    if view.get("summary"):
        hypotheses.append("Investigation view, unverified: " + view["summary"][:300])
    documented = ["Facts above are from the tenant-scoped alert row and any recorded investigation manifest."]
    spoken = f"For {a['short_code']} I have {len(observed)} observed fact(s) and {len(unknowns)} unverified gap(s)."
    return format_report(
        f"What is known vs unverified for {a['title']} ({a['short_code']}).",
        observed, documented, hypotheses, unknowns, spoken=spoken, extra={"alert_id": a["id"]},
    )
