"""End-to-end operator snapshot + proactive wake briefing for Tia."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.session import fetch_all, fetch_one
from app.services.soc_console_engines import build_engine_wall
from app.services.soc_console_proxmox import gather_proxmox_inventory

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def gather_operator_snapshot(*, hours: int = 24) -> Dict[str, Any]:
    """Single packed view: urgency + stack + hypervisor + fleet + compliance."""
    hours = max(1, min(int(hours or 24), 168))

    urgency = fetch_one(
        """
        SELECT
          (SELECT count(*)::int FROM security_alerts
             WHERE lower(severity) IN ('critical','high')
               AND status NOT IN ('closed','false_positive')
               AND created_at > now() - make_interval(hours => %s)) AS crit_high_open_window,
          (SELECT count(*)::int FROM security_alerts
             WHERE lower(severity) = 'critical'
               AND status NOT IN ('closed','false_positive')) AS critical_open,
          (SELECT count(*)::int FROM security_alerts
             WHERE lower(severity) = 'high'
               AND status NOT IN ('closed','false_positive')) AS high_open,
          (SELECT count(*)::int FROM incidents
             WHERE status IN ('open','in_progress','waiting_customer')) AS open_incidents,
          (SELECT count(*)::int FROM incidents
             WHERE status = 'waiting_customer') AS waiting_customer,
          (SELECT count(*)::int FROM appliances WHERE status = 'online') AS appliances_online,
          (SELECT count(*)::int FROM appliances) AS appliances_total,
          (SELECT count(*)::int FROM appliances
             WHERE status IS DISTINCT FROM 'online') AS appliances_not_online,
          (SELECT count(*)::int FROM sca_check_details
             WHERE upper(status) IN ('FAILED','FAIL')) AS patch_gaps,
          (SELECT count(*)::int FROM tenant_vulnerability_findings
             WHERE status = 'OPEN') AS open_vulns;
        """,
        (hours,),
    ) or {}

    top_alerts = fetch_all(
        """
        SELECT sa.id::text AS id, sa.alert_title AS title, sa.severity, sa.status,
               sa.destination_host AS host, sa.source_tool,
               t.short_code, t.name AS tenant_name,
               (sa.created_at AT TIME ZONE 'utc')::text AS ts
        FROM security_alerts sa
        JOIN tenants t ON t.id = sa.tenant_id
        WHERE sa.status NOT IN ('closed','false_positive')
          AND lower(sa.severity) IN ('critical','high')
        ORDER BY CASE lower(sa.severity) WHEN 'critical' THEN 0 ELSE 1 END,
                 sa.created_at DESC
        LIMIT 12;
        """
    ) or []

    top_incidents = fetch_all(
        """
        SELECT i.id::text AS id, i.incident_number, i.title, i.severity, i.status,
               t.short_code, t.name AS tenant_name,
               (i.updated_at AT TIME ZONE 'utc')::text AS ts
        FROM incidents i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.status IN ('open','in_progress','waiting_customer')
        ORDER BY CASE lower(i.severity)
                   WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
                 i.updated_at DESC
        LIMIT 10;
        """
    ) or []

    offline_appliances = fetch_all(
        """
        SELECT a.id::text AS id, a.appliance_name AS hostname, a.status, t.short_code,
               (a.last_seen_at AT TIME ZONE 'utc')::text AS last_seen_at
        FROM appliances a
        JOIN tenants t ON t.id = a.tenant_id
        WHERE a.status IS DISTINCT FROM 'online'
        ORDER BY a.last_seen_at DESC NULLS LAST
        LIMIT 10;
        """
    ) or []

    wall = build_engine_wall()
    lanes = wall.get("lanes") or []
    engines_offline = [
        {
            "id": L.get("id"),
            "label": L.get("label"),
            "vm": L.get("vm"),
            "hostname": L.get("hostname"),
            "status": L.get("status"),
            "probe_error": L.get("probe_error"),
        }
        for L in lanes
        if not L.get("reachable") and L.get("id") != "appliances"
    ]
    engines_online = sum(1 for L in lanes if L.get("reachable"))

    proxmox: Dict[str, Any] = {}
    try:
        # Stale-while-revalidate: never block dashboard/chat on a cold Proxmox SSH.
        proxmox = gather_proxmox_inventory(force=False, allow_stale=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("operator snapshot proxmox failed: %s", exc)
        proxmox = {"error": str(exc)[:120]}

    stopped_vms = [
        {"vmid": v.get("vmid"), "name": v.get("name"), "role": v.get("role")}
        for v in (proxmox.get("vms") or [])
        if (v.get("status") or "").lower() not in ("running", "", None)
        and v.get("status") is not None
    ]

    patch_by_tenant = fetch_all(
        """
        SELECT t.short_code, count(*)::int AS gaps
        FROM sca_check_details c
        JOIN tenants t ON t.id = c.tenant_id
        WHERE upper(c.status) IN ('FAILED','FAIL')
        GROUP BY t.short_code
        ORDER BY gaps DESC
        LIMIT 8;
        """
    ) or []

    needs_attention: List[str] = []
    if int(urgency.get("critical_open") or 0) > 0:
        needs_attention.append(f"{urgency['critical_open']} critical alert(s) open")
    if int(urgency.get("high_open") or 0) > 0:
        needs_attention.append(f"{urgency['high_open']} high alert(s) open")
    if int(urgency.get("waiting_customer") or 0) > 0:
        needs_attention.append(f"{urgency['waiting_customer']} incident(s) waiting on customer")
    if engines_offline:
        needs_attention.append(
            f"{len(engines_offline)} engine(s) unreachable: "
            + ", ".join(str(e.get("label") or e.get("id")) for e in engines_offline[:4])
        )
    if stopped_vms:
        needs_attention.append(
            f"{len(stopped_vms)} Proxmox VM(s) not running: "
            + ", ".join(f"{v.get('name')}({v.get('vmid')})" for v in stopped_vms[:4])
        )
    if int(urgency.get("appliances_not_online") or 0) > 0:
        needs_attention.append(
            f"{urgency['appliances_not_online']} appliance(s) not online"
        )

    # Investigations that did not complete (or need a person) are never hidden:
    # they are counted here until an analyst resolves them.
    from app.services.tia_investigation import open_review_summary

    review = open_review_summary()
    review_open = int(review.get("open_count") or 0)
    review_overdue = int(review.get("overdue_count") or 0)
    review_undeliverable = int(review.get("undeliverable_page_count") or 0)
    if review_undeliverable:
        needs_attention.insert(
            0,
            f"{review_undeliverable} page(s) could not be delivered (no recipient configured or delivery failed)",
        )
    # A fault in the investigation/notification path is shown, never hidden.
    from app.services import tia_schema

    try:
        tia_faults = [
            f for f in (tia_schema.readiness().get("faults") or []) if f.get("severity") == "fault"
        ]
    except Exception:  # noqa: BLE001
        tia_faults = [{"code": "readiness_check_failed", "message": "TIA readiness could not be checked"}]
    for fault in reversed(tia_faults):
        needs_attention.insert(0, f"TIA readiness fault: {fault.get('message') or fault.get('code')}")
    if review_open:
        needs_attention.insert(
            0,
            f"{review_open} TIA investigation(s) need analyst review"
            + (f" ({review_overdue} overdue)" if review_overdue else ""),
        )

    priority = "urgent" if (
        int(urgency.get("critical_open") or 0) > 0
        or engines_offline
        or stopped_vms
        or review_overdue
        or review_undeliverable
        or tia_faults
    ) else ("attention" if needs_attention else "clear")

    return {
        "generated_at": _utc_now(),
        "window_hours": hours,
        "priority": priority,
        "needs_attention": needs_attention,
        "review_queue": review,
        "urgency": urgency,
        "top_alerts": top_alerts,
        "top_incidents": top_incidents,
        "offline_appliances": offline_appliances,
        "stack": {
            "engines_total": len(lanes),
            "engines_online": engines_online,
            "engines_offline": engines_offline,
            "summary": wall.get("summary") or {},
            "lanes": lanes,
        },
        "proxmox": {
            "source": proxmox.get("source"),
            "hypervisor_node": proxmox.get("hypervisor_node"),
            "stopped_or_not_running": stopped_vms,
            "named": {
                k: {
                    "vmid": v.get("vmid"),
                    "name": v.get("name"),
                    "status": v.get("status"),
                    "vcpus": v.get("vcpus"),
                    "ram_configured_gb": v.get("ram_configured_gb"),
                    "ram_used_gb": v.get("ram_used_gb"),
                    "cpu_pct": v.get("cpu_pct"),
                }
                for k, v in (proxmox.get("named") or {}).items()
                if isinstance(v, dict)
            },
            "vms": [
                {
                    "vmid": v.get("vmid"),
                    "name": v.get("name"),
                    "role": v.get("role"),
                    "status": v.get("status"),
                    "vcpus": v.get("vcpus"),
                    "ram_configured_gb": v.get("ram_configured_gb"),
                    "ram_used_gb": v.get("ram_used_gb"),
                }
                for v in (proxmox.get("vms") or [])
            ],
        },
        "compliance": {
            "patch_gaps": int(urgency.get("patch_gaps") or 0),
            "open_vulns": int(urgency.get("open_vulns") or 0),
            "patch_gaps_by_tenant": patch_by_tenant,
        },
        "controls_available": [
            "update_alert (triage/false_positive/close)",
            "update_incident (status / waiting_customer / resolve)",
            "comment_incident",
            "answer stack/proxmox/patch/vuln/alert questions from live context",
        ],
    }


def render_critical_alert_read(snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Spoken + text answer for 'check critical alerts' from the live snapshot."""
    snap = snapshot or gather_operator_snapshot()
    urg = snap.get("urgency") or {}
    top = list(snap.get("top_alerts") or [])
    crit = int(urg.get("critical_open") or 0)
    high = int(urg.get("high_open") or 0)
    critical_rows = [a for a in top if str(a.get("severity") or "").lower() == "critical"]
    lead = critical_rows[0] if critical_rows else (top[0] if top else None)

    if crit == 0 and high == 0:
        spoken = "No critical or high alerts are open right now, boss."
    elif crit == 0:
        spoken = (
            f"No critical alerts are open, boss. "
            f"{high} high alert{'s' if high != 1 else ''} {'are' if high != 1 else 'is'} still open."
        )
    else:
        spoken = f"You have {crit} critical alert{'s' if crit != 1 else ''} open, boss."
        if high:
            spoken += f" {high} high as well."
    if lead:
        spoken += (
            f" Newest on the list: {lead.get('severity')} — {lead.get('title')} "
            f"for {lead.get('short_code') or lead.get('tenant_name') or 'a tenant'}."
        )
    spoken += " Tell me which one to open or update."

    lines = [
        f"**Critical open:** {crit}",
        f"**High open:** {high}",
        "",
        "**Newest critical and high**",
    ]
    if top:
        for a in top[:8]:
            lines.append(
                f"- [{a.get('severity')}] {a.get('short_code')}: {a.get('title')} ({a.get('status')})"
            )
    else:
        lines.append("- None open.")

    return {
        "agent": "Tia",
        "mode": "critical_alert_read",
        "answer": "\n".join(lines),
        "spoken_answer": spoken,
        "snapshot": snap,
        "provider": "operator-snapshot",
    }


def render_voice_answer(
    question: str = "",
    snapshot: Optional[Dict[str, Any]] = None,
    *,
    write_failed: bool = False,
) -> Dict[str, Any]:
    """Short spoken reply from the live snapshot. No model call."""
    snap = snapshot or gather_operator_snapshot()
    urg = snap.get("urgency") or {}
    top = list(snap.get("top_alerts") or [])
    crit = int(urg.get("critical_open") or 0)
    high = int(urg.get("high_open") or 0)
    incidents = int(urg.get("open_incidents") or 0)
    waiting = int(urg.get("waiting_customer") or 0)
    appl_on = int(urg.get("appliances_online") or 0)
    appl_total = int(urg.get("appliances_total") or 0)
    stack = snap.get("stack") or {}
    offline = list(stack.get("engines_offline") or [])
    online = int(stack.get("engines_online") or 0)
    total = int(stack.get("engines_total") or 0)
    gaps = int((snap.get("compliance") or {}).get("patch_gaps") or 0)
    vulns = int((snap.get("compliance") or {}).get("open_vulns") or 0)
    crit_rows = [a for a in top if str(a.get("severity") or "").lower() == "critical"]
    lead = crit_rows[0] if crit_rows else (top[0] if top else None)
    ql = (question or "").lower()

    def _who(row: Dict[str, Any]) -> str:
        raw = str(row.get("tenant_name") or row.get("short_code") or "a customer")
        return raw.replace("-", " ").replace("_", " ")

    def _lead_line() -> str:
        if not lead:
            return ""
        title = str(lead.get("title") or "an open alert").rstrip(".")
        return f"The one I'd open first is {title}, at {_who(lead)}."

    def _offline_names(limit: int = 3) -> str:
        return ", ".join(str(e.get("label") or e.get("id")) for e in offline[:limit])

    if re.search(r"\b(engine|stack|offline|reachable|health)\b", ql) and "alert" not in ql:
        if offline:
            spoken = (
                f"A few engines aren't answering. {_offline_names(3)}. "
                f"{online} of {total} are up. "
                f"The queue beside that is {crit} critical and {high} high."
            )
        else:
            spoken = (
                f"Stack's healthy. All {online} engines are answering. "
                f"What I'd actually worry about is the queue. {crit} critical, and {high} high."
            )
    elif re.search(r"\b(incident|incidents|case|cases)\b", ql) and "alert" not in ql:
        spoken = f"We've got {incidents} open incident{'s' if incidents != 1 else ''}."
        if waiting:
            spoken += f" {waiting} of those are waiting on the customer."
        incs = list(snap.get("top_incidents") or [])
        if incs:
            i0 = incs[0]
            spoken += f" The one on top is {i0.get('title')}, at {_who(i0)}."
    elif re.search(r"\b(patch|vuln)\b", ql):
        spoken = f"There are {gaps} patch gaps, and {vulns} open vulnerabilities."
        if crit or high:
            spoken += f" Alerts are separate from that. {crit} critical and {high} high."
    elif "appliance" in ql:
        spoken = f"{appl_on} of {appl_total} appliances are online."
        if crit:
            spoken += f" And yes, {crit} critical alerts are still sitting there."
    elif re.search(r"\b(hi|hey|hello|welcome)\b", ql):
        spoken = f"Hi Dad. {crit} critical are open, with {high} high behind them. {_lead_line()}"
        if offline:
            spoken += f" Also, {_offline_names(3)} {'are not' if len(offline) != 1 else 'is not'} answering."
        spoken += " What do you want to do?"
    else:
        if crit == 0 and high == 0:
            spoken = "Nothing critical or high is open right now."
        else:
            spoken = (
                f"Yeah. {crit} critical are open, and {high} high behind them. {_lead_line()}"
            )
        if offline:
            spoken += f" Heads up, {_offline_names(3)} {'are not' if len(offline) != 1 else 'is not'} answering."
        spoken += " Want me to open that one?"

    if write_failed:
        spoken += " I did not change a ticket. Name the alert and the status in one sentence and I will stage it."

    spoken = " ".join(spoken.split())
    if len(spoken) > 520:
        spoken = spoken[:517].rsplit(" ", 1)[0] + "."

    off_txt = _offline_names(4) if offline else "none"
    lines = [
        f"**Critical** {crit} · **High** {high} · **Incidents** {incidents}",
        f"**Engines** {online}/{total} · offline: {off_txt}",
        f"**Appliances** {appl_on}/{appl_total} · **Patch gaps** {gaps}",
        "",
        "**Newest alerts**",
    ]
    if top:
        for a in top[:5]:
            lines.append(
                f"- [{a.get('severity')}] {a.get('short_code')}: {a.get('title')} ({a.get('status')})"
            )
    else:
        lines.append("- None open.")

    return {
        "agent": "Tia",
        "mode": "voice_live",
        "answer": "\n".join(lines),
        "spoken_answer": spoken,
        "snapshot": snap,
        "provider": "tia-live",
    }


def render_wake_briefing(
    snapshot: Optional[Dict[str, Any]] = None,
    listed_alerts: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Proactive spoken + text welcome used on 'Hi Tia' with no follow-on question.

    When listed_alerts is provided it is the same ordered list stored on the conversation
    (so 'the first one' matches what was spoken). Otherwise the snapshot top-alerts are shown
    for dashboard routines that have no session.
    """
    snap = snapshot or gather_operator_snapshot()
    urg = snap.get("urgency") or {}
    stack = snap.get("stack") or {}
    attention = snap.get("needs_attention") or []
    offline = stack.get("engines_offline") or []
    online = int(stack.get("engines_online") or 0)
    total = int(stack.get("engines_total") or 0)

    crit = int(urg.get("critical_open") or 0)
    high = int(urg.get("high_open") or 0)
    open_inc = int(urg.get("open_incidents") or 0)
    gaps = int((snap.get("compliance") or {}).get("patch_gaps") or 0)
    top = list(listed_alerts) if listed_alerts is not None else list(snap.get("top_alerts") or [])
    first = (listed_alerts or top or [{}])[0] if (listed_alerts or top) else {}
    spoken = f"Hi Dad. {crit} critical and {high} high are open."
    if first.get("title"):
        spoken += f" The first one is {first.get('title')} for {first.get('short_code')}."
    spoken += " Ask me about that case, an engine, or a VM — I won't read the whole board."

    # Compact text card for the thread
    lines = [
        "Hi Dad.",
        "",
        "### Welcome back",
        f"**Priority:** {snap.get('priority')}",
        f"- Critical open: **{crit}** · High open: **{high}** · Incidents open: **{open_inc}**",
        f"- Engines: **{online}/{total}** reachable"
        + (f" · Offline: {', '.join(e.get('label') or '' for e in offline)}" if offline else ""),
        f"- Appliances online: **{urg.get('appliances_online')}/{urg.get('appliances_total')}**",
        f"- Patch gaps: **{gaps}** · Open vulns: **{(snap.get('compliance') or {}).get('open_vulns') or 0}**",
    ]
    if top:
        lines.append("")
        lines.append("**Top alerts**")
        for a in top[:5]:
            lines.append(
                f"- [{a.get('severity')}] {a.get('short_code')}: {a.get('title')} ({a.get('status')})"
            )
    if attention:
        lines.append("")
        lines.append("**Needs attention**")
        for item in attention:
            lines.append(f"- {item}")

    return {
        "agent": "Tia",
        "mode": "wake_briefing",
        "answer": "\n".join(lines),
        "spoken_answer": spoken,
        "snapshot": snap,
        "provider": "operator-snapshot",
    }
