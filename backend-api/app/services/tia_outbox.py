"""TIA notification outbox dispatcher (repair increment 2).

Pages are recorded as ``required`` rows inside the acceptance transaction. This
module sends them afterwards and tracks explicit states:

    required -> queued -> submitted -> delivered | failed -> acknowledged
                                              (cancelled if no longer needed)

Evidence rules
  submitted     the provider API accepted the message. It does not show a person
                saw it, and it is never reported as delivered.
  delivered     only when a provider receipt is recorded (record_delivery_receipt).
                No provider webhook is wired in this repository yet, so in
                practice rows stay ``submitted``.
  acknowledged  only through an authenticated analyst action (tia_review).

Recovery: the dispatcher claims rows with a lease. A crash after commit but before
sending leaves ``required``/``queued`` rows that the next tick re-claims. Sending
is at-least-once; a crash between the provider accepting and our update can send
one duplicate message, never zero.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.db.session import db_transaction
from app.services import tia_acceptance as acc
from app.services import tia_schema

logger = logging.getLogger(__name__)

LEASE_SECONDS = 120


class TransportError(RuntimeError):
    """A send failed. ``permanent`` failures are not retried."""

    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


@dataclass
class Receipt:
    provider: str
    message_id: Optional[str]


Transport = Callable[[str, str, str], Receipt]
_transport_override: Optional[Transport] = None


def set_transport(fn: Optional[Transport]) -> None:
    """Install a transport (tests use this; never a real contact)."""
    global _transport_override
    _transport_override = fn


def _default_transport(channel: str, recipient: str, message: str) -> Receipt:
    from app.services import soc_notifier as sn

    adapter = sn._ADAPTERS.get(channel)
    if adapter is None:
        raise TransportError(f"no adapter for channel '{channel}'", permanent=True)
    try:
        message_id = adapter(recipient, message)
    except sn.NotifyError as exc:
        text = str(exc)
        # Missing credentials and 4xx rejections will not fix themselves.
        permanent = "not configured" in text or text.startswith("HTTP 4")
        raise TransportError(text[:300], permanent=permanent) from exc
    return Receipt(provider=sn._provider_label(channel), message_id=message_id or None)


def _send(channel: str, recipient: str, message: str) -> Receipt:
    return (_transport_override or _default_transport)(channel, recipient, message)


def _backoff_seconds(attempts: int) -> int:
    try:
        base = int(os.getenv("TIA_NOTIFY_BACKOFF_SECONDS") or "30")
    except ValueError:
        base = 30
    return min(900, max(1, base) * (2 ** max(0, attempts - 1)))


# --------------------------------------------------------------------------
# claiming and sending
# --------------------------------------------------------------------------


def expand_blocked() -> int:
    """Give recipients to rows that were recorded while no roster was configured."""
    n = 0
    with db_transaction() as cur:
        rows = acc._all(
            cur,
            "SELECT * FROM tia_notifications WHERE recipient_address IS NULL "
            "AND state IN ('required','queued') ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 50;",
        )
        for row in rows:
            roster = tia_schema.oncall_roster() if row["level"] == 1 else tia_schema.escalation_roster()
            if not roster:
                continue
            first, rest = roster[0], roster[1:]
            cur.execute(
                "UPDATE tia_notifications SET recipient_address = %s, recipient_name = %s, "
                "blocked_reason = NULL, idempotency_key = %s, next_attempt_at = now() WHERE id = %s::uuid;",
                (first["address"], first["name"], f"{row['base_key']}:{acc._sha(first['address'])[:12]}", row["id"]),
            )
            for person in rest:
                cur.execute(
                    """
                    INSERT INTO tia_notifications
                        (tenant_id, alert_id, review_item_id, kind, level, base_key, idempotency_key, channel,
                         recipient_address, recipient_name, message_body, state, max_attempts, ack_due_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'required', %s, %s)
                    ON CONFLICT (idempotency_key) DO NOTHING;
                    """,
                    (
                        row["tenant_id"], row["alert_id"], row["review_item_id"], row["kind"], row["level"],
                        row["base_key"], f"{row['base_key']}:{acc._sha(person['address'])[:12]}", row["channel"],
                        person["address"], person["name"], row["message_body"], row["max_attempts"], row["ack_due_at"],
                    ),
                )
            n += 1
            if row["review_item_id"]:
                acc.sync_item_notification_state(cur, str(row["review_item_id"]))
    return n


def claim_batch(limit: int = 10) -> List[Dict[str, Any]]:
    """Lease rows for sending. A crashed worker's lease simply expires."""
    with db_transaction() as cur:
        return acc._all(
            cur,
            """
            UPDATE tia_notifications n
            SET state = 'queued', queued_at = now(), attempts = n.attempts + 1,
                locked_until = now() + make_interval(secs => %s)
            WHERE n.id IN (
                SELECT id FROM tia_notifications
                WHERE recipient_address IS NOT NULL
                  AND next_attempt_at <= now()
                  AND (state = 'required' OR (state = 'queued' AND locked_until < now()))
                ORDER BY next_attempt_at
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            RETURNING n.*, n.id::text AS id_text, n.review_item_id::text AS review_text;
            """,
            (LEASE_SECONDS, limit),
        )


def deliver(row: Dict[str, Any]) -> str:
    """Send one claimed row and record exactly what the provider told us."""
    row_id = row["id_text"]
    try:
        receipt = _send(row["channel"], row["recipient_address"], row["message_body"])
    except TransportError as exc:
        return _record_failure(row, str(exc)[:300], permanent=exc.permanent)
    except Exception as exc:  # noqa: BLE001
        return _record_failure(row, f"{type(exc).__name__}: {str(exc)[:200]}", permanent=False)
    with db_transaction() as cur:
        cur.execute(
            """
            UPDATE tia_notifications
            SET state = 'submitted', submitted_at = now(), provider = %s, provider_message_id = %s,
                delivery_evidence = 'provider_accepted', last_error = NULL, locked_until = NULL
            WHERE id = %s::uuid AND state = 'queued';
            """,
            (receipt.provider, receipt.message_id, row_id),
        )
        if row["review_text"]:
            acc.sync_item_notification_state(cur, row["review_text"])
    return "submitted"


def _record_failure(row: Dict[str, Any], error: str, *, permanent: bool) -> str:
    exhausted = permanent or int(row["attempts"]) >= int(row["max_attempts"])
    with db_transaction() as cur:
        if exhausted:
            cur.execute(
                "UPDATE tia_notifications SET state = 'failed', failed_at = now(), last_error = %s, locked_until = NULL "
                "WHERE id = %s::uuid AND state = 'queued';",
                (error, row["id_text"]),
            )
            logger.error("TIA page delivery FAILED id=%s attempts=%s: %s", row["id_text"], row["attempts"], error)
        else:
            cur.execute(
                "UPDATE tia_notifications SET state = 'required', last_error = %s, locked_until = NULL, "
                "next_attempt_at = now() + make_interval(secs => %s) WHERE id = %s::uuid AND state = 'queued';",
                (error, _backoff_seconds(int(row["attempts"])), row["id_text"]),
            )
        if row["review_text"]:
            acc.sync_item_notification_state(cur, row["review_text"])
    return "failed" if exhausted else "retry"


def deliver_pending(limit: int = 10) -> Dict[str, int]:
    counts = {"submitted": 0, "retry": 0, "failed": 0}
    for row in claim_batch(limit):
        counts[deliver(row)] += 1
    return counts


# --------------------------------------------------------------------------
# receipts and acknowledgement
# --------------------------------------------------------------------------


def receipts_configured() -> bool:
    """True when provider receipts can be authenticated (webhook secret and verify token set)."""
    return bool((os.getenv("WHATSAPP_APP_SECRET") or "").strip() and (os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN") or "").strip())


def record_delivery_receipt(provider_message_id: str) -> bool:
    """Record a provider delivery receipt. Only a submitted row can become delivered."""
    return apply_provider_status(provider_message_id, "delivered") == "delivered"


def apply_provider_status(provider_message_id: str, status: str, *, error: str = "") -> str:
    """Apply one authenticated provider status callback to the matching notification.

    Provider statuses (WhatsApp Cloud API): ``sent``, ``delivered``, ``read``, ``failed``.
      * ``sent``       provider accepted onward; nothing changes (still ``submitted``).
      * ``delivered``  the message reached the recipient's device: ``delivered``.
      * ``read``       the recipient opened it: ``delivered`` with read evidence.
                       A read receipt is NOT an analyst acknowledgement.
      * ``failed``     the provider could not deliver after accepting it: the page is
                       retried (bounded) or marked failed. It is never left as submitted.
    Receipts are idempotent and tolerate out-of-order arrival. Returns the resulting
    state, or ``unmatched`` / ``ignored``.
    """
    if not provider_message_id:
        return "unmatched"
    status = (status or "").strip().lower()
    with db_transaction() as cur:
        row = acc._one(
            cur,
            "SELECT id::text AS id, state, attempts, max_attempts, review_item_id::text AS review_text "
            "FROM tia_notifications WHERE provider_message_id = %s FOR UPDATE;",
            (provider_message_id,),
        )
        if not row:
            return "unmatched"
        result = "ignored"
        if status in ("delivered", "read"):
            evidence = "provider_read_receipt" if status == "read" else "provider_delivery_receipt"
            if row["state"] == "submitted":
                cur.execute(
                    "UPDATE tia_notifications SET state = 'delivered', delivered_at = now(), delivery_evidence = %s WHERE id = %s::uuid;",
                    (evidence, row["id"]),
                )
                result = "delivered"
            elif row["state"] in ("delivered", "acknowledged") and status == "read":
                cur.execute(
                    "UPDATE tia_notifications SET delivery_evidence = CASE WHEN delivery_evidence = 'provider_read_receipt' "
                    "THEN delivery_evidence ELSE %s END WHERE id = %s::uuid;",
                    (evidence, row["id"]),
                )
                result = row["state"]
        elif status == "failed" and row["state"] == "submitted":
            text = ("provider reported failure after accepting the message: " + (error or "no detail"))[:300]
            if int(row["attempts"]) >= int(row["max_attempts"]):
                cur.execute(
                    "UPDATE tia_notifications SET state = 'failed', failed_at = now(), last_error = %s WHERE id = %s::uuid;",
                    (text, row["id"]),
                )
                result = "failed"
            else:
                cur.execute(
                    "UPDATE tia_notifications SET state = 'required', last_error = %s, provider_message_id = NULL, "
                    "next_attempt_at = now() + make_interval(secs => %s) WHERE id = %s::uuid;",
                    (text, _backoff_seconds(int(row["attempts"])), row["id"]),
                )
                result = "retry"
        if result in ("delivered", "failed", "retry") and row["review_text"]:
            acc.sync_item_notification_state(cur, row["review_text"])
    return result


def acknowledge_item(cur, review_item_id: str, actor: str) -> Dict[str, int]:
    """Analyst acknowledgement: sent pages become acknowledged, unsent ones are cancelled."""
    acked = acc._all(
        cur,
        "UPDATE tia_notifications SET state = 'acknowledged', acknowledged_at = now(), acknowledged_by = %s, "
        "delivery_evidence = COALESCE(delivery_evidence, 'analyst_action') "
        "WHERE review_item_id = %s::uuid AND state IN ('submitted', 'delivered') RETURNING id::text AS id;",
        (actor, review_item_id),
    )
    cancelled = acc._all(
        cur,
        "UPDATE tia_notifications SET state = 'cancelled', locked_until = NULL "
        "WHERE review_item_id = %s::uuid AND state IN ('required', 'queued', 'failed') RETURNING id::text AS id;",
        (review_item_id,),
    )
    acc.sync_item_notification_state(cur, review_item_id)
    return {"acknowledged": len(acked), "cancelled": len(cancelled)}


def cancel_unsent(cur, review_item_id: str) -> int:
    """Resolving an item stops pages that were never sent. Sent pages keep their state."""
    rows = acc._all(
        cur,
        "UPDATE tia_notifications SET state = 'cancelled', locked_until = NULL "
        "WHERE review_item_id = %s::uuid AND state IN ('required', 'queued') RETURNING id::text AS id;",
        (review_item_id,),
    )
    acc.sync_item_notification_state(cur, review_item_id)
    return len(rows)


# --------------------------------------------------------------------------
# overdue acknowledgement -> configured escalation
# --------------------------------------------------------------------------


def escalate_overdue() -> int:
    """If a level-1 page is unacknowledged past its deadline, raise level 2."""
    raised = 0
    with db_transaction() as cur:
        rows = acc._all(
            cur,
            """
            SELECT n.*, n.id::text AS id_text, n.tenant_id::text AS tenant_text, n.alert_id::text AS alert_text,
                   n.review_item_id::text AS review_text
            FROM tia_notifications n
            LEFT JOIN tia_review_items r ON r.id = n.review_item_id
            WHERE n.kind = 'page' AND n.level = 1 AND n.escalated_at IS NULL
              AND n.ack_due_at IS NOT NULL AND n.ack_due_at < now()
              AND n.state NOT IN ('acknowledged', 'cancelled')
              AND (r.id IS NULL OR r.status = 'open')
            ORDER BY n.ack_due_at
            FOR UPDATE OF n SKIP LOCKED
            LIMIT 50;
            """,
        )
        done_bases = set()
        for row in rows:
            cur.execute("UPDATE tia_notifications SET escalated_at = now() WHERE id = %s::uuid;", (row["id_text"],))
            if row["base_key"] in done_bases:
                continue
            done_bases.add(row["base_key"])
            att = {"tenant_text": row["tenant_text"], "alert_text": row["alert_text"]}
            ids = acc._insert_notifications(
                cur, att=att, alert={}, kind="page", level=2, base_key=acc._sha(f"{row['base_key']}|L2"),
                roster=tia_schema.escalation_roster(), channel=tia_schema.escalation_channel(),
                body="[ESCALATION — page not acknowledged in time]\n" + row["message_body"],
                review_item_id=row["review_text"], ack_minutes=acc.page_ack_minutes(),
                blocked_reason="escalation_target_not_configured",
            )
            if row["review_text"]:
                acc._event(
                    cur, row["tenant_text"], row["review_text"], "ack_overdue_escalated",
                    detail={"level": 2, "notifications": len(ids), "target_configured": bool(tia_schema.escalation_roster())},
                )
                acc.sync_item_notification_state(cur, row["review_text"])
            raised += 1
    return raised


def reconcile_stale_attempts() -> int:
    """An attempt with no result and no recorded failure (e.g. the worker crashed
    mid-call) becomes an uncertain timeout, so the case gets a review item."""
    from app.services.soc_agent_client import _timeout_seconds

    grace = int(_timeout_seconds()) + 60
    with db_transaction() as cur:
        rows = acc._all(
            cur,
            "SELECT id::text AS id FROM tia_investigation_attempts WHERE status = 'dispatched' "
            "AND dispatched_at < now() - make_interval(secs => %s) ORDER BY dispatched_at LIMIT 20;",
            (grace,),
        )
    n = 0
    for row in rows:
        res = acc.record_attempt_failure(attempt_id=row["id"], category="timeout", timed_out=True, error="no_result_recorded")
        n += 1 if res.status == "accepted" else 0
    return n


# --------------------------------------------------------------------------
# worker
# --------------------------------------------------------------------------

_wake = threading.Event()
_started = False
_lock = threading.Lock()


def kick() -> None:
    """Ask the worker to run now (called after a commit)."""
    _wake.set()


def tick() -> Dict[str, Any]:
    """One maintenance pass. Does nothing unless the schema is ready."""
    status = tia_schema.check_schema()
    if not status.ok:
        return {"skipped": "schema_not_ready", "missing": status.missing}
    out: Dict[str, Any] = {}
    out["expanded"] = expand_blocked()
    out["delivery"] = deliver_pending()
    out["escalated"] = escalate_overdue()
    out["reconciled_attempts"] = reconcile_stale_attempts()
    try:
        from app.services.ai_alert_queue import requeue_dead_letters

        out["requeued"] = requeue_dead_letters()
    except Exception:  # noqa: BLE001
        logger.exception("dead-letter requeue failed")
    return out


def _enabled() -> bool:
    return (os.getenv("TIA_OUTBOX_ENABLED") or "true").strip().lower() not in ("0", "false", "no", "off")


def _loop() -> None:
    try:
        poll = float(os.getenv("TIA_OUTBOX_POLL_SECONDS") or "5")
    except ValueError:
        poll = 5.0
    while True:
        if _enabled():
            try:
                tick()
            except Exception:  # noqa: BLE001
                logger.exception("TIA outbox tick failed")
        _wake.wait(timeout=max(1.0, poll))
        _wake.clear()


def start_outbox_worker() -> None:
    global _started
    with _lock:
        if _started:
            return
        threading.Thread(target=_loop, name="tia-outbox", daemon=True).start()
        _started = True
        logger.info("TIA outbox worker started (enabled=%s)", _enabled())
