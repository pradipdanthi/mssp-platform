"""TIA readiness: required schema, notification configuration, and backlog.

The investigation pipeline depends on migrations 117 and 118. Code that needs
them calls ``require_schema()`` BEFORE doing work, so a missing migration stops
the work (it stays in the durable queue) instead of producing a false success or
a logging-only fallback. ``readiness()`` reports every operational fault in one
place for the SOC console.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SCHEMA_VERSION_REQUIRED = 118

# (table, columns that must exist). Columns are checked because 118 alters a
# table created by 117 and an old copy of 117 would otherwise pass a table check.
REQUIRED_OBJECTS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "tia_review_items",
        ("assigned_to", "reopened_count", "evidence_version", "analysis_available", "deadline_basis"),
    ),
    ("tia_review_events", ("review_item_id", "event_type")),
    ("tia_investigation_attempts", ("evidence_version", "accept_until", "outcome_uncertain")),
    ("tia_results", ("payload_hash", "applied", "apply_reason")),
    ("tia_acceptance_log", ("decision",)),
    ("tia_notifications", ("idempotency_key", "state", "ack_due_at", "locked_until")),
    ("tia_schema_version", ("component", "version")),
)


# Structures migrations 117 and 118 rely on for correctness, not just presence of
# tables: uniqueness (idempotency), the immutability trigger, forced RLS, and the
# CHECK that admits the notification states the code writes.
REQUIRED_UNIQUE: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("tia_notifications", ("idempotency_key",)),
    ("tia_results", ("attempt_id",)),
    ("tia_investigation_attempts", ("alert_id", "evidence_version", "attempt_no")),
)
REQUIRED_INDEXES: Tuple[str, ...] = ("uq_tia_review_items_alert_live", "idx_tia_notifications_work")
REQUIRED_TRIGGERS: Tuple[Tuple[str, str], ...] = (("tia_results", "trg_tia_results_immutable"),)
FORCED_RLS_TABLES: Tuple[str, ...] = (
    "tia_review_items", "tia_review_events", "tia_investigation_attempts", "tia_results", "tia_notifications",
)
NOTIFICATION_STATES = ("required", "queued", "submitted", "delivered", "failed", "acknowledged", "cancelled")


def _structure_faults(fetch_all) -> List[str]:
    """Return a list of missing structures (empty when the schema is intact)."""
    faults: List[str] = []
    for table, cols in REQUIRED_UNIQUE:
        rows = fetch_all(
            """
            SELECT array_agg(a.attname::text ORDER BY a.attname) AS cols
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
            WHERE i.indrelid = to_regclass(%s) AND i.indisunique AND i.indpred IS NULL
            GROUP BY i.indexrelid;
            """,
            (f"public.{table}",),
        )
        have = [sorted(r.get("cols") or []) for r in rows]
        if sorted(cols) not in have:
            faults.append(f"unique({table}.{'+'.join(cols)})")
    present = {
        r["indexname"]
        for r in fetch_all("SELECT indexname FROM pg_indexes WHERE schemaname = 'public';")
    }
    for name in REQUIRED_INDEXES:
        if name not in present:
            faults.append(f"index {name}")
    for table, trig in REQUIRED_TRIGGERS:
        rows = fetch_all(
            "SELECT tgenabled FROM pg_trigger WHERE tgrelid = to_regclass(%s) AND tgname = %s AND NOT tgisinternal;",
            (f"public.{table}", trig),
        )
        if not rows or str(rows[0].get("tgenabled")) not in ("O", "A"):
            faults.append(f"trigger {trig}")
    for table in FORCED_RLS_TABLES:
        rows = fetch_all(
            "SELECT relrowsecurity AS rls, relforcerowsecurity AS forced FROM pg_class WHERE oid = to_regclass(%s);",
            (f"public.{table}",),
        )
        if not rows or not (rows[0].get("rls") and rows[0].get("forced")):
            faults.append(f"forced row-level security on {table}")
    rows = fetch_all(
        "SELECT pg_get_constraintdef(c.oid) AS def FROM pg_constraint c "
        "WHERE c.conrelid = to_regclass('public.tia_notifications') AND c.contype = 'c';"
    )
    defs = " ".join(str(r.get("def") or "") for r in rows)
    for state in NOTIFICATION_STATES:
        if f"'{state}'" not in defs:
            faults.append(f"tia_notifications.state check lacks '{state}'")
    return faults


class SchemaNotReady(RuntimeError):
    """Required TIA schema is absent or the database cannot be checked."""

    def __init__(self, missing: List[str], detail: str = "") -> None:
        super().__init__("tia_schema_not_ready")
        self.missing = missing
        self.detail = detail


@dataclass
class SchemaStatus:
    ok: bool
    missing: List[str] = field(default_factory=list)
    detail: str = ""
    checked_at: float = 0.0


_cache: Optional[SchemaStatus] = None


def _ttl(ok: bool) -> float:
    # Re-check quickly after a failure so recovery is noticed; rarely when healthy.
    return 60.0 if ok else 3.0


def check_schema(force: bool = False) -> SchemaStatus:
    global _cache
    now = time.monotonic()
    if not force and _cache is not None and now - _cache.checked_at < _ttl(_cache.ok):
        return _cache
    from app.db.session import fetch_all

    missing: List[str] = []
    detail = ""
    try:
        for table, columns in REQUIRED_OBJECTS:
            exists = fetch_all("SELECT to_regclass(%s) IS NOT NULL AS present;", (f"public.{table}",))
            if not exists or not exists[0].get("present"):
                missing.append(table)
                continue
            rows = fetch_all(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s;",
                (table,),
            )
            have = {r["column_name"] for r in rows}
            for col in columns:
                if col not in have:
                    missing.append(f"{table}.{col}")
        if not missing:
            missing.extend(_structure_faults(fetch_all))
        if not missing:
            ver = fetch_all("SELECT version FROM tia_schema_version WHERE component = 'tia';")
            if not ver or int(ver[0]["version"]) < SCHEMA_VERSION_REQUIRED:
                missing.append(f"tia_schema_version>={SCHEMA_VERSION_REQUIRED}")
    except Exception as exc:  # noqa: BLE001
        detail = f"database check failed: {type(exc).__name__}"
        missing = missing or ["database_unavailable"]
    _cache = SchemaStatus(ok=not missing, missing=missing, detail=detail, checked_at=now)
    if not _cache.ok:
        logger.error("TIA schema not ready: missing=%s %s", missing, detail)
    return _cache


def reset_cache() -> None:
    global _cache
    _cache = None


def require_schema() -> None:
    """Raise SchemaNotReady unless migrations 117 and 118 are present."""
    status = check_schema()
    if not status.ok:
        raise SchemaNotReady(status.missing, status.detail)


# --------------------------------------------------------------------------
# Notification configuration
# --------------------------------------------------------------------------


def split_roster(raw: Optional[str]) -> List[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def oncall_roster() -> List[Dict[str, str]]:
    name = (os.getenv("SOC_ONCALL_NAME") or "Kevantic SOC on-call").strip()
    return [{"address": a, "name": name} for a in split_roster(os.getenv("SOC_ONCALL_WHATSAPP"))]


def escalation_roster() -> List[Dict[str, str]]:
    name = (os.getenv("SOC_ESCALATION_NAME") or "Kevantic SOC escalation").strip()
    return [{"address": a, "name": name} for a in split_roster(os.getenv("SOC_ONCALL_ESCALATION_WHATSAPP"))]


def escalation_channel() -> str:
    return (os.getenv("SOC_ESCALATION_CHANNEL") or "whatsapp").strip().lower()


def notification_config_faults() -> List[Dict[str, str]]:
    """Visible configuration faults. Never reports that paging works when it cannot."""
    faults: List[Dict[str, str]] = []
    channel = escalation_channel()
    if not oncall_roster():
        faults.append(
            {
                "code": "oncall_roster_not_configured",
                "severity": "fault",
                "message": "SOC_ONCALL_WHATSAPP is not set: no page can be sent to anyone.",
            }
        )
    if channel == "whatsapp":
        from app.services import tia_outbox

        if not tia_outbox.receipts_configured():
            faults.append(
                {
                    "code": "delivery_receipts_not_configured",
                    "severity": "warning",
                    "message": "WhatsApp delivery receipts are not configured (WHATSAPP_APP_SECRET / "
                    "WHATSAPP_WEBHOOK_VERIFY_TOKEN): pages stop at 'submitted' and delivery is reported as unknown.",
                }
            )
        if not (os.getenv("WHATSAPP_ACCESS_TOKEN") or "").strip() or not (
            os.getenv("WHATSAPP_PHONE_NUMBER_ID") or ""
        ).strip():
            faults.append(
                {
                    "code": "whatsapp_provider_not_configured",
                    "severity": "fault",
                    "message": "WhatsApp access token or phone number id is not set.",
                }
            )
        elif not (os.getenv("WHATSAPP_TEMPLATE_NAME") or "").strip():
            faults.append(
                {
                    "code": "whatsapp_template_not_configured",
                    "severity": "warning",
                    "message": "No approved WhatsApp template: business-initiated pages may be rejected outside a 24h window.",
                }
            )
    elif channel == "telegram":
        if not (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip():
            faults.append(
                {"code": "telegram_provider_not_configured", "severity": "fault", "message": "TELEGRAM_BOT_TOKEN is not set."}
            )
    elif channel != "webhook":
        faults.append(
            {"code": "unknown_escalation_channel", "severity": "fault", "message": f"Unknown SOC_ESCALATION_CHANNEL '{channel}'."}
        )
    from app.services import soc_agent_client

    transport = soc_agent_client.agent_transport()
    if soc_agent_client.soc_agent_enabled() and not transport["encrypted"]:
        faults.append(
            {
                "code": "agent_transport_not_encrypted",
                "severity": "warning" if transport["insecure_allowed"] else "fault",
                "message": "The SOC agent is reached over plain HTTP: alert evidence and the agent token cross the "
                "network unencrypted. Serve the agent over TLS and set SOC_AGENT_URL to https:// with SOC_AGENT_CA_BUNDLE.",
            }
        )
    elif transport["encrypted"] and not transport["ca_bundle_configured"]:
        faults.append(
            {
                "code": "agent_ca_not_pinned",
                "severity": "warning",
                "message": "Agent TLS is verified against the system CA store; pin the internal CA with SOC_AGENT_CA_BUNDLE.",
            }
        )
    if not escalation_roster():
        faults.append(
            {
                "code": "escalation_target_not_configured",
                "severity": "warning",
                "message": "SOC_ONCALL_ESCALATION_WHATSAPP is not set: an overdue acknowledgement cannot be escalated.",
            }
        )
    if (os.getenv("TIA_OUTBOX_ENABLED") or "true").strip().lower() in ("0", "false", "no", "off"):
        faults.append(
            {"code": "outbox_worker_disabled", "severity": "fault", "message": "TIA_OUTBOX_ENABLED is off: pages are recorded but never sent."}
        )
    return faults


def readiness() -> Dict[str, Any]:
    """One structured view of everything that can silently stop TIA from working."""
    schema = check_schema(force=True)
    faults: List[Dict[str, str]] = []
    backlog: Dict[str, Any] = {}
    if not schema.ok:
        faults.append(
            {
                "code": "schema_not_ready",
                "severity": "fault",
                "message": "Required TIA tables are missing: " + ", ".join(schema.missing)
                + ". Investigation work is held in the retry queue and is not being accepted.",
            }
        )
    else:
        from app.db.session import fetch_one

        try:
            row = fetch_one(
                """
                SELECT
                  (SELECT count(*) FROM tia_notifications
                     WHERE state IN ('required','queued') AND recipient_address IS NULL)::int AS blocked_notifications,
                  (SELECT count(*) FROM tia_notifications
                     WHERE state = 'required' AND recipient_address IS NOT NULL
                       AND created_at < now() - interval '5 minutes')::int AS stuck_notifications,
                  (SELECT count(*) FROM tia_notifications WHERE state = 'failed')::int AS failed_notifications,
                  (SELECT count(*) FROM tia_notifications
                     WHERE kind = 'page' AND state IN ('submitted','delivered')
                       AND ack_due_at < now())::int AS unacknowledged_overdue,
                  (SELECT count(*) FROM tia_review_items
                     WHERE status <> 'resolved' AND due_at < now())::int AS review_overdue,
                  (SELECT count(*) FROM tia_investigation_attempts
                     WHERE status = 'dispatched' AND dispatched_at < now() - interval '10 minutes')::int AS stale_attempts;
                """
            )
            backlog.update(row or {})
        except Exception as exc:  # noqa: BLE001
            faults.append(
                {"code": "backlog_query_failed", "severity": "fault", "message": f"Could not read TIA backlog: {type(exc).__name__}"}
            )
    try:
        from app.services.ai_alert_queue import dead_letter_count

        dead = dead_letter_count()
        backlog["dead_letters"] = dead
        if dead:
            faults.append(
                {
                    "code": "dead_letter_backlog",
                    "severity": "fault" if not schema.ok else "warning",
                    "message": f"{dead} investigation job(s) are in the dead-letter list and will be re-queued when healthy.",
                }
            )
    except Exception:  # noqa: BLE001
        backlog["dead_letters"] = None

    try:
        from app.services import ai_alert_queue, tia_jobs

        pipeline_on = ai_alert_queue._ai_pipeline_enabled()
        if not tia_jobs.schema_ready():
            if pipeline_on:
                faults.append(
                    {
                        "code": "jobs_schema_missing",
                        "severity": "fault",
                        "message": "Migration 120 (durable investigation jobs) is not applied: alerts use the legacy Redis queue, "
                        "which can lose work if the service restarts mid-analysis.",
                    }
                )
        else:
            jobs = tia_jobs.stats()
            backlog["jobs"] = jobs
            if jobs.get("expired_leases"):
                faults.append(
                    {"code": "job_leases_expired", "severity": "warning",
                     "message": f"{jobs['expired_leases']} investigation job(s) have an expired lease and will be recovered."}
                )
            if jobs.get("oldest_critical_age_s", 0) > 600:
                faults.append(
                    {"code": "critical_queue_stalled", "severity": "fault",
                     "message": f"A critical alert has waited {int(jobs['oldest_critical_age_s'])} s for an investigation worker."}
                )
            if pipeline_on and not jobs.get("workers_alive"):
                faults.append(
                    {"code": "job_workers_not_running", "severity": "fault",
                     "message": "No investigation worker threads are running in this process."}
                )
    except Exception:  # noqa: BLE001
        backlog["jobs"] = None

    faults.extend(notification_config_faults())
    if backlog.get("failed_notifications"):
        faults.append(
            {"code": "notification_delivery_failed", "severity": "fault", "message": f"{backlog['failed_notifications']} page(s) failed after bounded retries."}
        )
    if backlog.get("blocked_notifications"):
        faults.append(
            {"code": "notifications_waiting_for_recipient", "severity": "fault", "message": f"{backlog['blocked_notifications']} page(s) are waiting because no recipient is configured."}
        )
    if backlog.get("unacknowledged_overdue"):
        faults.append(
            {"code": "acknowledgement_overdue", "severity": "fault", "message": f"{backlog['unacknowledged_overdue']} page(s) have not been acknowledged by the deadline."}
        )
    if backlog.get("stale_attempts"):
        faults.append(
            {"code": "stale_attempts", "severity": "warning", "message": f"{backlog['stale_attempts']} investigation attempt(s) have had no result for over 10 minutes."}
        )
    from app.services import tia_investigation as tia

    mode = tia.investigation_mode()
    if mode == "manual_review":
        faults.append(
            {
                "code": "manual_review_mode_active",
                "severity": "warning",
                "message": "TIA_INVESTIGATION_MODE=manual_review: no model investigation runs; every qualifying case goes to an analyst.",
            }
        )
    from app.services import tia_conversation

    conversation_fault = tia_conversation.schema_fault()
    if conversation_fault:
        faults.append(
            {
                "code": "conversation_schema_missing",
                "severity": "warning",
                "message": f"TIA conversation (migration 119) is not ready: {conversation_fault}. "
                "Chat falls back to the legacy path; 'yes, open it' and verified dashboard actions are unavailable.",
            }
        )
    ready = not any(f["severity"] == "fault" for f in faults)
    return {
        "ready": ready,
        "conversation": {
            "ok": conversation_fault is None,
            "required_version": tia_conversation.SCHEMA_VERSION_REQUIRED,
            "fault": conversation_fault,
        },
        "investigation_mode": mode,
        "schema": {"ok": schema.ok, "missing": schema.missing, "required_version": SCHEMA_VERSION_REQUIRED},
        "faults": faults,
        "backlog": backlog,
        "deadlines": {
            "basis": "provisional",
            "note": "Review deadlines are provisional defaults, not approved customer SLAs.",
        },
    }
