"""Side effects with a stable logical identity, so retries and crashes do not repeat them.

An effect is identified by WHAT it is (kind + alert + evidence version), not by the attempt that
produced it. Every attempt that reaches the effect is appended to its history.

Local effects (a ticket note in our own database) commit the effect row and the write in one
transaction: after a crash either both exist or neither does, and a retry finds the committed row.

External effects (a note in another system) cannot share our transaction, so:

  1. the intent is committed first as ``uncertain`` with an in-flight lease,
  2. the external call is made carrying a marker (the logical key),
  3. success commits ``committed`` with the external reference.

If the response is lost, or the process dies between 2 and 3, the row stays ``uncertain``. The
next attempt first asks the external system whether a write carrying the marker exists
(reconcile) and only writes again if it does not. While a lease is live, another worker does not
touch the effect. This narrows duplicates to the case where the external search itself is
inconsistent; it is not exactly-once delivery.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Dict, Optional, Protocol

from app.db.session import db_transaction, fetch_one

logger = logging.getLogger(__name__)

IN_FLIGHT_LEASE_SECONDS = 120


def logical_key(kind: str, alert_id: str, evidence_version: str) -> str:
    return hashlib.sha256(f"{kind}|{alert_id}|{evidence_version}".encode()).hexdigest()[:40]


def _claim(cur, *, kind: str, key: str, tenant_id: str, alert_id: str, incident_id: Optional[str], evidence_version: str, attempt_id: Optional[str]) -> Dict[str, Any]:
    cur.execute(
        """
        INSERT INTO tia_effects (logical_key, effect_kind, tenant_id, alert_id, incident_id, evidence_version, first_attempt_id)
        VALUES (%s, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s::uuid)
        ON CONFLICT (logical_key) DO NOTHING;
        """,
        (key, kind, tenant_id, alert_id, incident_id, evidence_version, attempt_id),
    )
    cur.execute(
        "SELECT id::text AS id, status, target_ref, attempt_history, "
        "extract(epoch FROM (now() - uncertain_since))::int AS uncertain_age FROM tia_effects WHERE logical_key = %s FOR UPDATE;",
        (key,),
    )
    return dict(cur.fetchone())


def _note_attempt(cur, effect_id: str, attempt_id: Optional[str], action: str) -> None:
    cur.execute(
        "UPDATE tia_effects SET attempt_history = attempt_history || %s::jsonb WHERE id = %s::uuid;",
        (json.dumps([{"attempt_id": attempt_id, "action": action}]), effect_id),
    )


def apply_local(
    *, kind: str, tenant_id: str, alert_id: str, incident_id: Optional[str], evidence_version: str,
    attempt_id: Optional[str], content_hash: str, write: Callable[[Any], str],
) -> Dict[str, Any]:
    """Run ``write(cur)`` at most once per logical key, atomically with the ledger row."""
    key = logical_key(kind, alert_id, evidence_version)
    with db_transaction() as cur:
        row = _claim(cur, kind=kind, key=key, tenant_id=tenant_id, alert_id=alert_id, incident_id=incident_id,
                     evidence_version=evidence_version, attempt_id=attempt_id)
        if row["status"] == "committed":
            _note_attempt(cur, row["id"], attempt_id, "already_committed")
            return {"outcome": "already_committed", "effect_id": row["id"], "target_ref": row["target_ref"], "logical_key": key}
        ref = write(cur)
        cur.execute(
            "UPDATE tia_effects SET status = 'committed', target_ref = %s, committed_at = now(), content_hash = %s, incident_id = coalesce(incident_id, %s::uuid), "
            "attempt_history = attempt_history || %s::jsonb WHERE id = %s::uuid;",
            (ref, content_hash, incident_id, json.dumps([{"attempt_id": attempt_id, "action": "committed"}]), row["id"]),
        )
    return {"outcome": "committed", "effect_id": row["id"], "target_ref": ref, "logical_key": key}


def skip(*, kind: str, tenant_id: str, alert_id: str, evidence_version: str, attempt_id: Optional[str], reason: str) -> Dict[str, Any]:
    key = logical_key(kind, alert_id, evidence_version)
    with db_transaction() as cur:
        row = _claim(cur, kind=kind, key=key, tenant_id=tenant_id, alert_id=alert_id, incident_id=None, evidence_version=evidence_version, attempt_id=attempt_id)
        if row["status"] == "committed":
            return {"outcome": "already_committed", "effect_id": row["id"], "target_ref": row["target_ref"], "logical_key": key}
        cur.execute(
            "UPDATE tia_effects SET status = 'skipped', skip_reason = %s, attempt_history = attempt_history || %s::jsonb WHERE id = %s::uuid;",
            (reason, json.dumps([{"attempt_id": attempt_id, "action": f"skipped:{reason}"}]), row["id"]),
        )
    return {"outcome": "skipped", "reason": reason, "effect_id": row["id"], "logical_key": key}


class ExternalTicket(Protocol):
    def find_by_marker(self, ticket_ref: str, marker: str) -> Optional[str]: ...
    def add_note(self, ticket_ref: str, marker: str, text: str) -> str: ...


class OutcomeUnknown(Exception):
    """The external call may or may not have taken effect (timeout, lost response)."""


def apply_external(
    *, client: ExternalTicket, ticket_ref: str, tenant_id: str, alert_id: str, evidence_version: str,
    attempt_id: Optional[str], text: str, kind: str = "external_ticket_note",
) -> Dict[str, Any]:
    key = logical_key(kind, alert_id, evidence_version)
    marker = f"tia-effect:{key}"
    with db_transaction() as cur:
        row = _claim(cur, kind=kind, key=key, tenant_id=tenant_id, alert_id=alert_id, incident_id=None, evidence_version=evidence_version, attempt_id=attempt_id)
        if row["status"] == "committed":
            _note_attempt(cur, row["id"], attempt_id, "already_committed")
            return {"outcome": "already_committed", "target_ref": row["target_ref"], "logical_key": key}
        if row["status"] == "uncertain" and row["uncertain_age"] is not None and row["uncertain_age"] < IN_FLIGHT_LEASE_SECONDS:
            _note_attempt(cur, row["id"], attempt_id, "deferred_in_flight")
            return {"outcome": "in_flight_elsewhere", "logical_key": key}
        reconcile = row["status"] == "uncertain"
        cur.execute(
            "UPDATE tia_effects SET status = 'uncertain', uncertain_since = now(), attempt_history = attempt_history || %s::jsonb WHERE id = %s::uuid;",
            (json.dumps([{"attempt_id": attempt_id, "action": "reconcile_then_write" if reconcile else "write_intent"}]), row["id"]),
        )
        effect_id = row["id"]

    if reconcile:
        found = client.find_by_marker(ticket_ref, marker)
        if found:
            _finish(effect_id, found, attempt_id, "reconciled_existing")
            return {"outcome": "reconciled_existing", "target_ref": found, "logical_key": key}
    try:
        ref = client.add_note(ticket_ref, marker, text)
    except OutcomeUnknown:
        _touch(effect_id, attempt_id, "outcome_unknown")
        return {"outcome": "uncertain", "logical_key": key}
    except Exception as exc:  # noqa: BLE001  - a definite failure: nothing was written
        _revert(effect_id, attempt_id, f"failed:{type(exc).__name__}")
        return {"outcome": "failed", "error": type(exc).__name__, "logical_key": key}
    _finish(effect_id, ref, attempt_id, "committed")
    return {"outcome": "committed", "target_ref": ref, "logical_key": key}


def _finish(effect_id: str, ref: str, attempt_id: Optional[str], action: str) -> None:
    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_effects SET status = 'committed', target_ref = %s, committed_at = now(), uncertain_since = NULL, "
            "attempt_history = attempt_history || %s::jsonb WHERE id = %s::uuid;",
            (ref, json.dumps([{"attempt_id": attempt_id, "action": action}]), effect_id),
        )


def _touch(effect_id: str, attempt_id: Optional[str], action: str) -> None:
    with db_transaction() as cur:
        # Leave it uncertain, but let the lease lapse so the next attempt reconciles promptly.
        cur.execute(
            "UPDATE tia_effects SET uncertain_since = now() - make_interval(secs => %s), attempt_history = attempt_history || %s::jsonb WHERE id = %s::uuid;",
            (IN_FLIGHT_LEASE_SECONDS, json.dumps([{"attempt_id": attempt_id, "action": action}]), effect_id),
        )


def _revert(effect_id: str, attempt_id: Optional[str], action: str) -> None:
    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_effects SET status = 'pending', uncertain_since = NULL, attempt_history = attempt_history || %s::jsonb WHERE id = %s::uuid;",
            (json.dumps([{"attempt_id": attempt_id, "action": action}]), effect_id),
        )


def get(kind: str, alert_id: str, evidence_version: str) -> Optional[Dict[str, Any]]:
    return fetch_one(
        "SELECT id::text AS id, status, target_ref, attempt_history, skip_reason, (committed_at AT TIME ZONE 'utc')::text AS committed_at "
        "FROM tia_effects WHERE logical_key = %s;",
        (logical_key(kind, alert_id, evidence_version),),
    ) or None
