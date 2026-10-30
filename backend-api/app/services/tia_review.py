"""Analyst review queue for TIA investigations (repair increment 2).

Server-side rules, independent of anything the UI shows:

  * Only SOC roles reach this module (the routes require them); customer roles are
    refused with 403 for lists, details, counts and every action.
  * Acknowledge records that a person took ownership of the page. It never
    resolves the item and never touches the security case.
  * Resolve needs a written note. Reopen needs a written note. Both are audited.
  * Every transition appends a tia_review_events row and an audit_logs row.

Role matrix
    acknowledge   platform_admin, soc_manager, soc_analyst
    assign        platform_admin, soc_manager (assign anyone);
                  soc_analyst (claim for self only)
    resolve       platform_admin, soc_manager (any item);
                  soc_analyst (only an item assigned to them)
    reopen        platform_admin, soc_manager
    read          all three
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.db.session import db_transaction
from app.services import tia_acceptance as acc
from app.services import tia_outbox, tia_schema
from app.services.audit_service import write_audit_event

MANAGER_ROLES = ("platform_admin", "soc_manager")
ALL_ROLES = ("platform_admin", "soc_manager", "soc_analyst")
MIN_NOTE = 5


class ReviewError(Exception):
    """A refused action. ``http`` maps to the status code the route returns."""

    def __init__(self, http: int, message: str) -> None:
        super().__init__(message)
        self.http = http
        self.message = message


def _actor(user: Dict[str, Any]) -> str:
    return str(user.get("email") or user.get("id") or "unknown")[:200]


def _require_role(user: Dict[str, Any], allowed) -> str:
    role = str(user.get("role") or "")
    if role not in allowed:
        raise ReviewError(403, "You do not have permission to perform this action")
    return role


def _note(value: Optional[str], *, required: bool) -> str:
    text = (value or "").strip()
    if required and len(text) < MIN_NOTE:
        raise ReviewError(422, f"A note of at least {MIN_NOTE} characters is required")
    return text[:1000]


def _mask(address: Optional[str]) -> Optional[str]:
    if not address:
        return None
    return ("*" * max(0, len(address) - 4)) + address[-4:]


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------

_LIST_SQL = """
    SELECT r.id::text AS id, r.alert_id::text AS alert_id, r.tenant_id::text AS tenant_id,
           t.name AS customer_name, t.short_code AS customer_code,
           sa.alert_title AS case_title, sa.status AS case_status,
           r.status, r.reason_code, r.execution_status, r.error_category,
           r.source_severity, r.assessed_priority, r.notify_urgency, r.notification_state,
           r.assigned_to, r.assigned_at::text AS assigned_at,
           r.occurrences, r.reopened_count, r.analysis_available, r.highest_finding,
           r.model_review_requested, r.deadline_basis,
           r.first_seen_at::text AS first_seen_at, r.last_seen_at::text AS last_seen_at,
           r.due_at::text AS due_at,
           EXTRACT(EPOCH FROM (now() - r.first_seen_at))::bigint AS age_seconds,
           EXTRACT(EPOCH FROM (r.due_at - now()))::bigint AS seconds_to_deadline,
           (r.due_at < now() AND r.status <> 'resolved') AS overdue,
           r.reasons, r.limited_evidence,
           COALESCE((SELECT jsonb_object_agg(s.state, s.n) FROM (
               SELECT state, count(*) AS n FROM tia_notifications n
               WHERE n.review_item_id = r.id GROUP BY state) s), '{}'::jsonb) AS notification_counts
    FROM tia_review_items r
    JOIN tenants t ON t.id = r.tenant_id
    JOIN security_alerts sa ON sa.id = r.alert_id
"""


def summary(tenant_id: Optional[str] = None) -> Dict[str, Any]:
    tia_schema.require_schema()
    with db_transaction() as cur:
        row = acc._one(
            cur,
            """
            SELECT
              count(*) FILTER (WHERE status <> 'resolved')::int AS open_count,
              count(*) FILTER (WHERE status = 'open')::int AS unacknowledged_count,
              count(*) FILTER (WHERE status <> 'resolved' AND due_at < now())::int AS overdue_count,
              count(*) FILTER (WHERE status <> 'resolved' AND notify_urgency = 'page')::int AS page_count,
              count(*) FILTER (WHERE status <> 'resolved' AND notification_state IN ('no_recipients_configured', 'page_failed'))::int AS undeliverable_page_count,
              count(*) FILTER (WHERE status <> 'resolved' AND assigned_to IS NULL)::int AS unassigned_count,
              min(due_at) FILTER (WHERE status <> 'resolved')::text AS next_due_at
            FROM tia_review_items
            WHERE (%s::uuid IS NULL OR tenant_id = %s::uuid);
            """,
            (tenant_id, tenant_id),
        )
    data = dict(row or {})
    data["deadline_basis"] = "provisional"
    return data


def list_items(
    *, status: Optional[str] = None, tenant_id: Optional[str] = None, assigned_to: Optional[str] = None,
    include_resolved: bool = False, limit: int = 100, offset: int = 0,
) -> Dict[str, Any]:
    tia_schema.require_schema()
    where, params = ["(%s OR r.status <> 'resolved')"], [include_resolved]
    if status:
        where.append("r.status = %s")
        params.append(status)
    if tenant_id:
        where.append("r.tenant_id = %s::uuid")
        params.append(tenant_id)
    if assigned_to:
        where.append("r.assigned_to = %s")
        params.append(assigned_to)
    params.extend([limit, offset])
    with db_transaction() as cur:
        items = acc._all(
            cur,
            _LIST_SQL + " WHERE " + " AND ".join(where)
            + " ORDER BY (r.status = 'resolved'), r.assessed_priority, r.due_at LIMIT %s OFFSET %s;",
            tuple(params),
        )
    return {"items": items, "summary": summary(tenant_id), "deadline_basis": "provisional"}


def get_item(item_id: str) -> Dict[str, Any]:
    tia_schema.require_schema()
    with db_transaction() as cur:
        item = acc._one(cur, _LIST_SQL + " WHERE r.id = %s::uuid;", (item_id,))
        if not item:
            raise ReviewError(404, "Review item not found")
        events = acc._all(
            cur,
            "SELECT event_type, actor, from_status, to_status, attempt_id::text AS attempt_id, detail, created_at::text AS at "
            "FROM tia_review_events WHERE review_item_id = %s::uuid ORDER BY created_at, id;",
            (item_id,),
        )
        attempts = acc._all(
            cur,
            "SELECT id::text AS id, attempt_no, status, outcome_uncertain, transport_error, "
            "dispatched_at::text AS dispatched_at, closed_at::text AS closed_at, evidence_version "
            "FROM tia_investigation_attempts WHERE alert_id = %s::uuid ORDER BY dispatched_at DESC LIMIT 20;",
            (item["alert_id"],),
        )
        results = acc._all(
            cur,
            "SELECT id::text AS id, attempt_id::text AS attempt_id, first_source, execution_status, error_category, "
            "verdict, confidence, disposition, applied, apply_reason, material, late, accepted_at::text AS at "
            "FROM tia_results WHERE alert_id = %s::uuid ORDER BY accepted_at DESC LIMIT 20;",
            (item["alert_id"],),
        )
        notes = acc._all(
            cur,
            "SELECT id::text AS id, kind, level, channel, recipient_address, recipient_name, state, blocked_reason, "
            "attempts, max_attempts, last_error, delivery_evidence, provider, "
            "created_at::text AS created_at, submitted_at::text AS submitted_at, delivered_at::text AS delivered_at, "
            "failed_at::text AS failed_at, acknowledged_at::text AS acknowledged_at, acknowledged_by, "
            "ack_due_at::text AS ack_due_at, escalated_at::text AS escalated_at "
            "FROM tia_notifications WHERE review_item_id = %s::uuid ORDER BY created_at;",
            (item_id,),
        )
    for n in notes:
        n["recipient"] = _mask(n.pop("recipient_address"))
    item.update(events=events, attempts=attempts, results=results, notifications=notes)
    return item


# --------------------------------------------------------------------------
# actions
# --------------------------------------------------------------------------


def _lock(cur, item_id: str) -> Dict[str, Any]:
    row = acc._one(cur, "SELECT * FROM tia_review_items WHERE id = %s::uuid FOR UPDATE;", (item_id,))
    if not row:
        raise ReviewError(404, "Review item not found")
    return row


def _audit(user: Dict[str, Any], action: str, item: Dict[str, Any], details: Dict[str, Any]) -> None:
    write_audit_event(
        action=f"tia.review.{action}",
        entity_type="tia_review_item",
        entity_id=str(item["id"]),
        tenant_id=str(item["tenant_id"]),
        actor_user_id=str(user.get("id")) if user.get("id") else None,
        actor_email=user.get("email"),
        actor_role=user.get("role"),
        details=details,
    )


def acknowledge(item_id: str, user: Dict[str, Any], note: Optional[str] = None) -> Dict[str, Any]:
    _require_role(user, ALL_ROLES)
    tia_schema.require_schema()
    actor = _actor(user)
    with db_transaction() as cur:
        item = _lock(cur, item_id)
        if item["status"] == "resolved":
            raise ReviewError(409, "Item is resolved; reopen it first")
        if item["status"] == "acknowledged":
            return {"ok": True, "changed": False, "status": "acknowledged"}
        cur.execute(
            "UPDATE tia_review_items SET status = 'acknowledged', acknowledged_at = now() WHERE id = %s::uuid;",
            (item_id,),
        )
        counts = tia_outbox.acknowledge_item(cur, item_id, actor)
        acc._event(cur, str(item["tenant_id"]), item_id, "acknowledged", actor=actor,
                   from_status="open", to_status="acknowledged",
                   detail={"note": _note(note, required=False), **counts, "case_status_unchanged": True})
    _audit(user, "acknowledge", item, {"notifications": counts})
    return {"ok": True, "changed": True, "status": "acknowledged", **counts}


def assign(item_id: str, user: Dict[str, Any], assignee: Optional[str]) -> Dict[str, Any]:
    role = _require_role(user, ALL_ROLES)
    tia_schema.require_schema()
    actor = _actor(user)
    target = (assignee or actor).strip()[:200]
    if not target:
        raise ReviewError(422, "assignee is required")
    if role == "soc_analyst" and target != actor:
        raise ReviewError(403, "Analysts can only assign an item to themselves")
    with db_transaction() as cur:
        item = _lock(cur, item_id)
        if item["status"] == "resolved":
            raise ReviewError(409, "Item is resolved; reopen it first")
        if item["assigned_to"] == target:
            return {"ok": True, "changed": False, "assigned_to": target}
        if role == "soc_analyst" and item["assigned_to"] and item["assigned_to"] != actor:
            raise ReviewError(403, "Item is assigned to someone else; ask a manager to reassign")
        cur.execute(
            "UPDATE tia_review_items SET assigned_to = %s, assigned_at = now() WHERE id = %s::uuid;",
            (target, item_id),
        )
        acc._event(cur, str(item["tenant_id"]), item_id, "assigned", actor=actor,
                   from_status=item["status"], to_status=item["status"],
                   detail={"from": item["assigned_to"], "to": target})
    _audit(user, "assign", item, {"from": item["assigned_to"], "to": target})
    return {"ok": True, "changed": True, "assigned_to": target}


def resolve(item_id: str, user: Dict[str, Any], note: Optional[str]) -> Dict[str, Any]:
    role = _require_role(user, ALL_ROLES)
    tia_schema.require_schema()
    actor = _actor(user)
    text = _note(note, required=True)
    with db_transaction() as cur:
        item = _lock(cur, item_id)
        if item["status"] == "resolved":
            return {"ok": True, "changed": False, "status": "resolved"}
        if role == "soc_analyst" and item["assigned_to"] != actor:
            raise ReviewError(403, "Analysts can resolve only items assigned to them")
        cur.execute(
            "UPDATE tia_review_items SET status = 'resolved', resolved_at = now(), resolved_by = %s, "
            "resolution_note = %s WHERE id = %s::uuid;",
            (actor, text, item_id),
        )
        cancelled = tia_outbox.cancel_unsent(cur, item_id)
        acc._event(cur, str(item["tenant_id"]), item_id, "resolved", actor=actor,
                   from_status=item["status"], to_status="resolved",
                   detail={"note": text, "cancelled_notifications": cancelled, "case_status_unchanged": True})
    _audit(user, "resolve", item, {"note_length": len(text)})
    return {"ok": True, "changed": True, "status": "resolved"}


def reopen(item_id: str, user: Dict[str, Any], note: Optional[str]) -> Dict[str, Any]:
    _require_role(user, MANAGER_ROLES)
    tia_schema.require_schema()
    actor = _actor(user)
    text = _note(note, required=True)
    with db_transaction() as cur:
        item = _lock(cur, item_id)
        if item["status"] != "resolved":
            raise ReviewError(409, "Only a resolved item can be reopened")
        live = acc._one(
            cur,
            "SELECT id::text AS id FROM tia_review_items WHERE alert_id = %s AND status <> 'resolved';",
            (item["alert_id"],),
        )
        if live:
            raise ReviewError(409, "A newer open review item already exists for this case")
        minutes = tia_schema_due_minutes(item["assessed_priority"])
        cur.execute(
            "UPDATE tia_review_items SET status = 'open', reopened_count = reopened_count + 1, reopened_at = now(), "
            "resolved_at = NULL, resolved_by = NULL, acknowledged_at = NULL, "
            "due_at = now() + make_interval(mins => %s) WHERE id = %s::uuid;",
            (minutes, item_id),
        )
        acc._event(cur, str(item["tenant_id"]), item_id, "reopened", actor=actor,
                   from_status="resolved", to_status="open", detail={"note": text, "deadline_minutes": minutes})
    _audit(user, "reopen", item, {"note_length": len(text)})
    return {"ok": True, "changed": True, "status": "open"}


def tia_schema_due_minutes(priority: str) -> int:
    from app.services import tia_investigation as tia

    sev = {"P1": "critical", "P2": "high", "P3": "medium", "P4": "low"}.get(priority or "", "unknown")
    return tia._due_minutes(sev)


def readiness() -> Dict[str, Any]:
    return tia_schema.readiness()
