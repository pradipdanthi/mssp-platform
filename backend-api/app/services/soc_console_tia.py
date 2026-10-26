"""Tia — named SOC agent briefing brain + safe ticket actions.

Tia answers like a human SOC colleague using live control-plane facts.
Ticket updates are explicit, audited, and never invent containment.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.db.session import fetch_all, fetch_one, fetch_one_write

logger = logging.getLogger(__name__)

TIA_NAME = "Tia"
TIA_SYSTEM = """You are Tia, the Kevantic NikTiar SOC Agent — warm, sharp Tier-1/2 colleague with
END-TO-END live access across the MSSP platform (not a chatbot limited to one feed).

You can see and reason over:
- operator_snapshot: urgency (critical/high alerts, incidents), engine reachability, appliances,
  Proxmox VM vCPU/RAM/power, patch gaps, open vulns, needs_attention
- platform_visibility: engine wall, control-plane host metrics, topic deep-dives (patch/vuln/proxmox)
- briefing: recent critical/high, FPs closed, incidents touched, notifications, AI triage
- tenant_context when a customer is scoped

Safe controls you MAY execute via TIA_ACTIONS when the boss clearly asks:
- update_alert / update_incident / comment_incident
You must NEVER claim host isolation, firewall blocks, or destructive containment ran unless CONTEXT
explicitly records that action. Propose containment; do not invent it.

CONVERSATION RULES:
1. Point-to-point: answer the latest question first. No unrelated stack dump.
2. On wake / "welcome back" / "what needs attention": lead with urgency → top alerts → stack health.
3. If operator_snapshot or proxmox/patch detail is present, USE IT — never say you lack access to
   those facts.
4. Patch gaps ≠ CVE vulns. Proxmox guest RAM ≠ container /proc RAM on mssp-control.
5. Prefer 3–8 spoken sentences. Longer lists go under Details.
6. Use ONLY CONTEXT facts. Never invent customers, hosts, CVEs, or engine status.

If the boss asks you to update a ticket/alert, end with:
<<<TIA_ACTIONS
[{"type":"update_alert","alert_id":"<uuid>","status":"false_positive","note":"reason"}]
TIA_ACTIONS>>>
Allowed: update_alert (new|triaged|incident_created|false_positive|closed);
update_incident (open|in_progress|waiting_customer|resolved|closed + optional note);
comment_incident (incident_id + note).
Always end with:
<<<TIA_SPOKEN
...
TIA_SPOKEN>>>
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def gather_tia_briefing(
    *,
    tenant_id: Optional[str] = None,
    hours_away: int = 24,
) -> Dict[str, Any]:
    """Facts Tia needs for 'what happened while I was away' style questions."""
    hours = max(1, min(int(hours_away or 24), 168))

    if tenant_id:
        critical = fetch_all(
            """
            SELECT sa.id::text AS id, sa.alert_title AS title, sa.severity, sa.status,
                   sa.source_tool, sa.destination_host, sa.ai_verdict, sa.ai_triage_status,
                   sa.ai_recommended_action, sa.customer_visible,
                   t.name AS tenant_name, t.short_code,
                   (sa.created_at AT TIME ZONE 'utc')::text AS ts
            FROM security_alerts sa
            JOIN tenants t ON t.id = sa.tenant_id
            WHERE sa.created_at > now() - make_interval(hours => %s)
              AND sa.tenant_id = %s::uuid
              AND lower(sa.severity) IN ('critical','high')
              AND sa.status NOT IN ('closed','false_positive')
            ORDER BY CASE lower(sa.severity) WHEN 'critical' THEN 0 ELSE 1 END, sa.created_at DESC
            LIMIT 40;
            """,
            (hours, tenant_id),
        )
        fp_closed = fetch_all(
            """
            SELECT sa.id::text AS id, sa.alert_title AS title, sa.severity, sa.status,
                   t.short_code, t.name AS tenant_name,
                   (sa.updated_at AT TIME ZONE 'utc')::text AS ts
            FROM security_alerts sa
            JOIN tenants t ON t.id = sa.tenant_id
            WHERE sa.updated_at > now() - make_interval(hours => %s)
              AND sa.tenant_id = %s::uuid
              AND sa.status = 'false_positive'
            ORDER BY sa.updated_at DESC
            LIMIT 25;
            """,
            (hours, tenant_id),
        )
        incidents = fetch_all(
            """
            SELECT i.id::text AS id, i.incident_number, i.title, i.severity, i.status,
                   i.customer_visible_summary, i.customer_action_required,
                   t.short_code, t.name AS tenant_name,
                   (i.updated_at AT TIME ZONE 'utc')::text AS ts
            FROM incidents i
            JOIN tenants t ON t.id = i.tenant_id
            WHERE i.updated_at > now() - make_interval(hours => %s)
              AND i.tenant_id = %s::uuid
            ORDER BY i.updated_at DESC
            LIMIT 25;
            """,
            (hours, tenant_id),
        )
        notified = fetch_all(
            """
            SELECT n.id::text AS id, n.notification_type, n.status, n.provider,
                   left(n.message_body, 160) AS snippet,
                   t.short_code, t.name AS tenant_name,
                   (n.created_at AT TIME ZONE 'utc')::text AS ts
            FROM notification_events n
            JOIN tenants t ON t.id = n.tenant_id
            WHERE n.created_at > now() - make_interval(hours => %s)
              AND n.tenant_id = %s::uuid
            ORDER BY n.created_at DESC
            LIMIT 20;
            """,
            (hours, tenant_id),
        )
        ai_acted = fetch_all(
            """
            SELECT sa.id::text AS id, sa.alert_title AS title, sa.severity,
                   sa.ai_verdict, sa.ai_triage_status, sa.ai_containment_suggestion,
                   t.short_code,
                   (coalesce(sa.ai_triaged_at, sa.updated_at) AT TIME ZONE 'utc')::text AS ts
            FROM security_alerts sa
            JOIN tenants t ON t.id = sa.tenant_id
            WHERE coalesce(sa.ai_triaged_at, sa.updated_at) > now() - make_interval(hours => %s)
              AND sa.tenant_id = %s::uuid
              AND sa.ai_verdict IS NOT NULL
            ORDER BY coalesce(sa.ai_triaged_at, sa.updated_at) DESC
            LIMIT 25;
            """,
            (hours, tenant_id),
        )
        counts = fetch_one(
            """
            SELECT
              (SELECT COUNT(*)::int FROM security_alerts
                 WHERE created_at > now() - make_interval(hours => %s)
                   AND tenant_id = %s::uuid
                   AND lower(severity) IN ('critical','high')
                   AND status NOT IN ('closed','false_positive')) AS critical_open,
              (SELECT COUNT(*)::int FROM security_alerts
                 WHERE updated_at > now() - make_interval(hours => %s)
                   AND tenant_id = %s::uuid
                   AND status = 'false_positive') AS false_positives_closed,
              (SELECT COUNT(*)::int FROM incidents
                 WHERE status IN ('open','in_progress','waiting_customer')
                   AND tenant_id = %s::uuid) AS open_incidents,
              (SELECT COUNT(*)::int FROM notification_events
                 WHERE created_at > now() - make_interval(hours => %s)
                   AND tenant_id = %s::uuid
                   AND status IN ('sent','delivered','queued')) AS customer_notifications;
            """,
            (hours, tenant_id, hours, tenant_id, tenant_id, hours, tenant_id),
        )
    else:
        critical = fetch_all(
            """
            SELECT sa.id::text AS id, sa.alert_title AS title, sa.severity, sa.status,
                   sa.source_tool, sa.destination_host, sa.ai_verdict, sa.ai_triage_status,
                   sa.ai_recommended_action, sa.customer_visible,
                   t.name AS tenant_name, t.short_code,
                   (sa.created_at AT TIME ZONE 'utc')::text AS ts
            FROM security_alerts sa
            JOIN tenants t ON t.id = sa.tenant_id
            WHERE sa.created_at > now() - make_interval(hours => %s)
              AND lower(sa.severity) IN ('critical','high')
              AND sa.status NOT IN ('closed','false_positive')
            ORDER BY CASE lower(sa.severity) WHEN 'critical' THEN 0 ELSE 1 END, sa.created_at DESC
            LIMIT 40;
            """,
            (hours,),
        )
        fp_closed = fetch_all(
            """
            SELECT sa.id::text AS id, sa.alert_title AS title, sa.severity, sa.status,
                   t.short_code, t.name AS tenant_name,
                   (sa.updated_at AT TIME ZONE 'utc')::text AS ts
            FROM security_alerts sa
            JOIN tenants t ON t.id = sa.tenant_id
            WHERE sa.updated_at > now() - make_interval(hours => %s)
              AND sa.status = 'false_positive'
            ORDER BY sa.updated_at DESC
            LIMIT 25;
            """,
            (hours,),
        )
        incidents = fetch_all(
            """
            SELECT i.id::text AS id, i.incident_number, i.title, i.severity, i.status,
                   i.customer_visible_summary, i.customer_action_required,
                   t.short_code, t.name AS tenant_name,
                   (i.updated_at AT TIME ZONE 'utc')::text AS ts
            FROM incidents i
            JOIN tenants t ON t.id = i.tenant_id
            WHERE i.updated_at > now() - make_interval(hours => %s)
            ORDER BY i.updated_at DESC
            LIMIT 25;
            """,
            (hours,),
        )
        notified = fetch_all(
            """
            SELECT n.id::text AS id, n.notification_type, n.status, n.provider,
                   left(n.message_body, 160) AS snippet,
                   t.short_code, t.name AS tenant_name,
                   (n.created_at AT TIME ZONE 'utc')::text AS ts
            FROM notification_events n
            JOIN tenants t ON t.id = n.tenant_id
            WHERE n.created_at > now() - make_interval(hours => %s)
            ORDER BY n.created_at DESC
            LIMIT 20;
            """,
            (hours,),
        )
        ai_acted = fetch_all(
            """
            SELECT sa.id::text AS id, sa.alert_title AS title, sa.severity,
                   sa.ai_verdict, sa.ai_triage_status, sa.ai_containment_suggestion,
                   t.short_code,
                   (coalesce(sa.ai_triaged_at, sa.updated_at) AT TIME ZONE 'utc')::text AS ts
            FROM security_alerts sa
            JOIN tenants t ON t.id = sa.tenant_id
            WHERE coalesce(sa.ai_triaged_at, sa.updated_at) > now() - make_interval(hours => %s)
              AND sa.ai_verdict IS NOT NULL
            ORDER BY coalesce(sa.ai_triaged_at, sa.updated_at) DESC
            LIMIT 25;
            """,
            (hours,),
        )
        counts = fetch_one(
            """
            SELECT
              (SELECT COUNT(*)::int FROM security_alerts
                 WHERE created_at > now() - make_interval(hours => %s)
                   AND lower(severity) IN ('critical','high')
                   AND status NOT IN ('closed','false_positive')) AS critical_open,
              (SELECT COUNT(*)::int FROM security_alerts
                 WHERE updated_at > now() - make_interval(hours => %s)
                   AND status = 'false_positive') AS false_positives_closed,
              (SELECT COUNT(*)::int FROM incidents
                 WHERE status IN ('open','in_progress','waiting_customer')) AS open_incidents,
              (SELECT COUNT(*)::int FROM notification_events
                 WHERE created_at > now() - make_interval(hours => %s)
                   AND status IN ('sent','delivered','queued')) AS customer_notifications;
            """,
            (hours, hours, hours),
        )

    return {
        "agent": TIA_NAME,
        "generated_at": _utc_now(),
        "window_hours": hours,
        "counts": counts or {},
        "critical_or_high_open": critical or [],
        "false_positives_closed": fp_closed or [],
        "incidents_touched": incidents or [],
        "customer_notifications": notified or [],
        "ai_triage_actions": ai_acted or [],
        "rules": {
            "containment": "proposal_only",
            "customer_notify": "from notification_events only",
        },
    }


def parse_tia_blocks(answer: str) -> Tuple[str, str, List[Dict[str, Any]]]:
    """Split human answer, spoken line, and action list from Tia response."""
    text = answer or ""
    spoken = ""
    actions: List[Dict[str, Any]] = []

    m_spoken = re.search(
        r"<<<TIA_SPOKEN\s*([\s\S]*?)\s*TIA_SPOKEN>>>",
        text,
        flags=re.IGNORECASE,
    )
    if m_spoken:
        spoken = m_spoken.group(1).strip()
        text = text[: m_spoken.start()] + text[m_spoken.end() :]

    m_act = re.search(
        r"<<<TIA_ACTIONS\s*([\s\S]*?)\s*TIA_ACTIONS>>>",
        text,
        flags=re.IGNORECASE,
    )
    if m_act:
        raw = m_act.group(1).strip()
        text = text[: m_act.start()] + text[m_act.end() :]
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                actions = [a for a in parsed if isinstance(a, dict)]
        except json.JSONDecodeError:
            logger.warning("Tia actions JSON parse failed")

    clean = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not spoken:
        parts = re.split(r"(?<=[.!?])\s+", clean)
        spoken = " ".join(parts[:3])[:600]
    return clean, spoken, actions[:5]


def apply_tia_actions(
    actions: List[Dict[str, Any]],
    *,
    actor_user_id: Optional[str],
    actor_email: str,
) -> List[Dict[str, Any]]:
    """Execute allowed ticket updates. Returns per-action results."""
    results: List[Dict[str, Any]] = []
    for action in actions:
        atype = str(action.get("type") or "").strip().lower()
        try:
            if atype == "update_alert":
                results.append(_update_alert(action, actor_email=actor_email))
            elif atype == "update_incident":
                results.append(
                    _update_incident(action, actor_user_id=actor_user_id, actor_email=actor_email)
                )
            elif atype == "comment_incident":
                results.append(
                    _comment_incident(action, actor_user_id=actor_user_id, actor_email=actor_email)
                )
            else:
                results.append({"ok": False, "type": atype, "error": "unsupported_action"})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Tia action failed: %s", atype)
            results.append({"ok": False, "type": atype, "error": str(exc)[:200]})
    return results


_ALERT_STATUSES = {"new", "triaged", "incident_created", "false_positive", "closed"}
_INC_STATUSES = {"open", "in_progress", "waiting_customer", "resolved", "closed"}


def _update_alert(action: Dict[str, Any], *, actor_email: str) -> Dict[str, Any]:
    alert_id = str(action.get("alert_id") or "").strip()
    status_v = str(action.get("status") or "").strip().lower()
    note = str(action.get("note") or "")[:500]
    if not alert_id or status_v not in _ALERT_STATUSES:
        return {"ok": False, "type": "update_alert", "error": "invalid_alert_or_status"}
    try:
        UUID(alert_id)
    except ValueError:
        return {"ok": False, "type": "update_alert", "error": "invalid_alert_id"}

    hide = status_v == "false_positive"
    row = fetch_one_write(
        """
        UPDATE security_alerts
        SET status = %s,
            customer_visible = CASE WHEN %s THEN false ELSE customer_visible END,
            ai_triage_status = coalesce(ai_triage_status, 'tia_updated'),
            updated_at = now()
        WHERE id = %s::uuid
        RETURNING id::text, alert_title, status;
        """,
        (status_v, hide, alert_id),
    )
    if not row:
        return {"ok": False, "type": "update_alert", "error": "not_found"}
    _audit(actor_email, "tia.update_alert", "security_alert", alert_id, {"status": status_v, "note": note})
    return {"ok": True, "type": "update_alert", "alert": row, "note": note}


def _update_incident(
    action: Dict[str, Any], *, actor_user_id: Optional[str], actor_email: str
) -> Dict[str, Any]:
    incident_id = str(action.get("incident_id") or "").strip()
    status_v = str(action.get("status") or "").strip().lower()
    note = str(action.get("note") or "")[:800]
    if not incident_id or status_v not in _INC_STATUSES:
        return {"ok": False, "type": "update_incident", "error": "invalid_incident_or_status"}
    try:
        UUID(incident_id)
    except ValueError:
        return {"ok": False, "type": "update_incident", "error": "invalid_incident_id"}

    row = fetch_one_write(
        """
        UPDATE incidents
        SET status = %s, updated_at = now()
        WHERE id = %s::uuid
        RETURNING id::text, incident_number, status, title;
        """,
        (status_v, incident_id),
    )
    if not row:
        return {"ok": False, "type": "update_incident", "error": "not_found"}
    if note:
        _comment_incident(
            {"incident_id": incident_id, "note": note},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
    _audit(actor_email, "tia.update_incident", "incident", incident_id, {"status": status_v})
    return {"ok": True, "type": "update_incident", "incident": row}


def _comment_incident(
    action: Dict[str, Any], *, actor_user_id: Optional[str], actor_email: str
) -> Dict[str, Any]:
    incident_id = str(action.get("incident_id") or "").strip()
    note = str(action.get("note") or "").strip()
    if not incident_id or len(note) < 3:
        return {"ok": False, "type": "comment_incident", "error": "invalid_note"}
    try:
        UUID(incident_id)
    except ValueError:
        return {"ok": False, "type": "comment_incident", "error": "invalid_incident_id"}

    exists = fetch_one("SELECT id::text FROM incidents WHERE id = %s::uuid", (incident_id,))
    if not exists:
        return {"ok": False, "type": "comment_incident", "error": "not_found"}

    # created_by_user_id may be null if actor id missing
    row = fetch_one_write(
        """
        INSERT INTO incident_comments (incident_id, created_by_user_id, visibility, comment_text)
        VALUES (%s::uuid, %s::uuid, 'internal', %s)
        RETURNING id::text;
        """,
        (incident_id, actor_user_id, f"[Tia] {note}"[:4000]),
    ) if actor_user_id else fetch_one_write(
        """
        INSERT INTO incident_comments (incident_id, created_by_user_id, visibility, comment_text)
        VALUES (%s::uuid, NULL, 'internal', %s)
        RETURNING id::text;
        """,
        (incident_id, f"[Tia] {note}"[:4000]),
    )
    if actor_user_id:
        fetch_one_write(
            """
            INSERT INTO incident_timeline (incident_id, event_type, visibility, title, details, created_by_user_id)
            VALUES (%s::uuid, 'comment', 'internal', %s, %s, %s::uuid);
            """,
            (incident_id, "Tia ticket update", note[:2000], actor_user_id),
        )
    else:
        fetch_one_write(
            """
            INSERT INTO incident_timeline (incident_id, event_type, visibility, title, details, created_by_user_id)
            VALUES (%s::uuid, 'comment', 'internal', %s, %s, NULL);
            """,
            (incident_id, "Tia ticket update", note[:2000]),
        )
    _audit(actor_email, "tia.comment_incident", "incident", incident_id, {"note": note[:200]})
    return {"ok": True, "type": "comment_incident", "comment_id": (row or {}).get("id")}


def _audit(actor_email: str, action: str, entity_type: str, entity_id: str, details: Dict[str, Any]) -> None:
    try:
        fetch_one_write(
            """
            INSERT INTO audit_logs (actor_user_id, action, entity_type, entity_id, details)
            SELECT id, %s, %s, %s::uuid, %s::jsonb
            FROM platform_users WHERE email = %s
            LIMIT 1;
            """,
            (action, entity_type, entity_id, json.dumps(details), actor_email),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Tia audit log failed")
