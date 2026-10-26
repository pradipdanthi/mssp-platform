"""End-to-end operator snapshot + proactive wake briefing for Tia."""

from __future__ import annotations

import logging
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

    priority = "urgent" if (
        int(urgency.get("critical_open") or 0) > 0 or engines_offline or stopped_vms
    ) else ("attention" if needs_attention else "clear")

    return {
        "generated_at": _utc_now(),
        "window_hours": hours,
        "priority": priority,
        "needs_attention": needs_attention,
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


def render_wake_briefing(snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Proactive spoken + text welcome used on 'Hi Tia' with no follow-on question."""
    snap = snapshot or gather_operator_snapshot()
    urg = snap.get("urgency") or {}
    stack = snap.get("stack") or {}
    attention = snap.get("needs_attention") or []
    top = snap.get("top_alerts") or []
    offline = stack.get("engines_offline") or []
    online = int(stack.get("engines_online") or 0)
    total = int(stack.get("engines_total") or 0)

    spoken_parts = ["Hello boss — welcome back."]

    crit = int(urg.get("critical_open") or 0)
    high = int(urg.get("high_open") or 0)
    if crit or high:
        spoken_parts.append(
            f"You have {crit} critical and {high} high alert{'s' if (crit + high) != 1 else ''} open."
        )
        if top:
            a0 = top[0]
            spoken_parts.append(
                f"Top item: {a0.get('severity')} — {a0.get('title')} "
                f"for {a0.get('short_code') or a0.get('tenant_name') or 'a tenant'}."
            )
        spoken_parts.append("That needs attention.")
    else:
        spoken_parts.append("No critical or high alerts are open right now.")

    open_inc = int(urg.get("open_incidents") or 0)
    waiting = int(urg.get("waiting_customer") or 0)
    if open_inc:
        bit = f"{open_inc} open incident{'s' if open_inc != 1 else ''}"
        if waiting:
            bit += f", {waiting} waiting on the customer"
        spoken_parts.append(bit + ".")

    if offline:
        names = ", ".join(str(e.get("label") or e.get("id")) for e in offline[:3])
        spoken_parts.append(f"Stack watch: {len(offline)} engine(s) unreachable — {names}.")
    else:
        spoken_parts.append(f"End-to-end stack looks healthy — {online} of {total} engines reachable.")

    gaps = int((snap.get("compliance") or {}).get("patch_gaps") or 0)
    if gaps:
        spoken_parts.append(f"Also on the board: {gaps} patch gaps.")

    if attention and snap.get("priority") == "urgent" and crit == 0 and high == 0:
        spoken_parts.append("Urgent items: " + "; ".join(attention[:3]) + ".")

    spoken_parts.append("What do you want to dig into?")
    spoken = " ".join(spoken_parts)

    # Compact text card for the thread
    lines = [
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
