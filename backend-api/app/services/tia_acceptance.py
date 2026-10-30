"""TIA result acceptance (repair increment 2).

ONE authenticated, tenant-scoped, transactional function accepts every
investigation outcome, whether it arrives as the HTTP reply, as a late callback,
or as a failure the control plane itself observed (timeout, unreachable agent).

In a single database transaction it:
  1. checks the job / attempt / tenant / alert / evidence-version binding,
  2. records the result (immutable, one per attempt) and its provenance,
  3. decides whether the result may update the authoritative alert fields,
  4. applies the review lifecycle and the escalation policy,
  5. records every required notification in an outbox.

Nothing external happens here. The outbox (tia_outbox) sends after commit and can
recover after a crash. A database or schema failure raises, so the caller does
NOT acknowledge and the work stays in the retry path.

Review lifecycle (explicit transitions)
  create    no live item, review required            -> new item (open)
  recur     live item, same obligation again         -> occurrences+1; deadline
            can only move earlier; first_seen_at never changes; priority only rises
  reopen    resolved item, MATERIAL new finding      -> same item reopened, new deadline
  suppress  resolved item, non-material recurrence   -> history event only
  analysis  later analysis succeeds, no review needed-> flag + event; never auto-resolves
  resolve   analyst action only (tia_review)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.db.session import db_transaction
from app.services import tia_investigation as tia
from app.services import tia_schema

logger = logging.getLogger(__name__)

TERMINAL_ALERT_STATUSES = frozenset({"closed", "resolved", "false_positive"})
HUMAN_TRIAGE_STATUSES = frozenset({"accepted", "rejected"})

_FINDING_RANK = {
    "analysis_unavailable": 1,
    "verdict:BENIGN_FALSE_POSITIVE": 0,
    "verdict:SUSPICIOUS": 2,
    "verdict:MALICIOUS": 3,
}


@dataclass
class AcceptanceResult:
    status: str  # accepted | duplicate | conflict | rejected
    reason: Optional[str] = None
    attempt_id: Optional[str] = None
    result_id: Optional[str] = None
    applied: bool = False
    material: bool = False
    late: bool = False
    review_item_id: Optional[str] = None
    review_action: Optional[str] = None
    notification_ids: List[str] = field(default_factory=list)
    decision: Dict[str, Any] = field(default_factory=dict)
    outcome: Optional[tia.Outcome] = None
    triage: Optional[Dict[str, Any]] = None

    @property
    def handled(self) -> bool:
        return self.status in ("accepted", "duplicate")


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _one(cur, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None


def _all(cur, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int(os.getenv(name) or default)
    except ValueError:
        value = default
    return max(lo, min(value, hi))


def late_window_seconds() -> int:
    """How long after dispatch a result is still accepted (default 24 h)."""
    return _int_env("TIA_LATE_RESULT_WINDOW_SECONDS", 86400, 300, 7 * 86400)


def page_ack_minutes() -> int:
    """Provisional: minutes before an unacknowledged page is escalated."""
    return _int_env("TIA_PAGE_ACK_MINUTES", 15, 1, 24 * 60)


def outage_window_seconds() -> int:
    return _int_env("TIA_OUTAGE_NOTICE_WINDOW_SECONDS", 3600, 60, 24 * 3600)


def payload_hash(outcome: tia.Outcome) -> str:
    """Stable identity of the finding, independent of transport and timing."""
    material = {
        "status": outcome.execution_status,
        "category": outcome.error_category,
        "llm": outcome.llm,
    }
    blob = json.dumps(material, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _log(cur, *, source: str, decision: str, reason: Optional[str], tenant_id=None, alert_id=None, attempt_id=None, phash=None) -> None:
    cur.execute(
        """
        INSERT INTO tia_acceptance_log (tenant_id, alert_id, attempt_id, source, decision, reason, payload_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s);
        """,
        (tenant_id, alert_id, attempt_id, source, decision, reason, phash),
    )


def _valid_uuid(value: Any) -> Optional[str]:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


_EVIDENCE_SQL = """
    SELECT md5(concat_ws('|',
        coalesce(sa.severity, ''), coalesce(sa.alert_title, ''), coalesce(sa.alert_description, ''),
        coalesce(host(sa.source_ip), ''), coalesce(host(sa.destination_ip), ''),
        coalesce(sa.destination_host, ''), coalesce(sa.source_user, ''),
        coalesce(sa.asset_id::text, ''), coalesce(sa.raw_event::text, ''), coalesce(sa.hashes_raw, ''),
        coalesce(sa.parent_process, ''), coalesce(sa.parent_command_line, ''), coalesce(sa.hash_sha256, ''),
        coalesce(sa.win_eventdata::text, '')
    )) AS version
    FROM security_alerts sa
    WHERE sa.id = %s::uuid AND sa.tenant_id = %s::uuid
"""


def evidence_version(cur, alert_id: str, tenant_id: str) -> Optional[str]:
    row = _one(cur, _EVIDENCE_SQL, (alert_id, tenant_id))
    return row["version"] if row else None


def _lock_alert(cur, alert_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    return _one(
        cur,
        """
        SELECT sa.id::text AS id, sa.tenant_id::text AS tenant_id, sa.severity, sa.status,
               sa.alert_title, sa.ai_triage_status, sa.destination_host,
               t.name AS tenant_name, t.short_code,
               pa.hostname AS asset_hostname, pa.criticality AS asset_criticality
        FROM security_alerts sa
        JOIN tenants t ON t.id = sa.tenant_id
        LEFT JOIN protected_assets pa ON pa.id = sa.asset_id
        WHERE sa.id = %s::uuid AND sa.tenant_id = %s::uuid
        FOR UPDATE OF sa;
        """,
        (alert_id, tenant_id),
    )


# --------------------------------------------------------------------------
# attempts
# --------------------------------------------------------------------------


def open_attempt(*, alert_id: str, tenant_id: str) -> Dict[str, Any]:
    """Record the attempt BEFORE the agent is called. Raises if the schema is absent.

    The returned ids bind the agent's reply and any later callback to this exact
    tenant, alert, and evidence version.
    """
    tia_schema.require_schema()
    with db_transaction() as cur:
        alert = _lock_alert(cur, alert_id, tenant_id)
        if not alert:
            raise LookupError("alert not found for tenant")
        version = evidence_version(cur, alert_id, tenant_id)
        nxt = _one(
            cur,
            "SELECT COALESCE(MAX(attempt_no), 0) + 1 AS n FROM tia_investigation_attempts "
            "WHERE alert_id = %s::uuid AND evidence_version = %s;",
            (alert_id, version),
        )
        attempt_no = int(nxt["n"])
        row = _one(
            cur,
            """
            INSERT INTO tia_investigation_attempts
                (tenant_id, alert_id, evidence_version, job_key, attempt_no, accept_until)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s, now() + make_interval(secs => %s))
            RETURNING id::text AS id;
            """,
            (tenant_id, alert_id, version, f"{alert_id}:{version}", attempt_no, late_window_seconds()),
        )
        if urgent_on_intake(alert):
            _enqueue_intake_page(cur, alert=alert, version=version)
    return {
        "attempt_id": row["id"],
        "job_id": f"{alert_id}:{version}",
        "attempt_no": attempt_no,
        "evidence_version": version,
        "tenant_id": tenant_id,
        "alert_id": alert_id,
    }


# --------------------------------------------------------------------------
# the unified acceptance entry points
# --------------------------------------------------------------------------


def accept_result(
    *,
    source: str,
    attempt_id: Any,
    claimed_tenant_id: Optional[str] = None,
    claimed_alert_id: Optional[str] = None,
    claimed_job_id: Optional[str] = None,
    claimed_evidence_version: Optional[str] = None,
    raw: Any,
    fallback: Optional[Dict[str, Any]] = None,
) -> AcceptanceResult:
    """Accept one agent result. ``source`` is 'http' or 'callback'.

    Raises tia_schema.SchemaNotReady or a database error WITHOUT having changed
    anything, so the caller must not acknowledge. A rejection (unknown attempt,
    tenant/job mismatch, conflicting payload) is a normal return and is logged.
    """
    tia_schema.require_schema()
    attempt_uuid = _valid_uuid(attempt_id)
    try:
        with db_transaction() as cur:
            if not attempt_uuid:
                _log(cur, source=source, decision="rejected", reason="invalid_attempt_id")
                return AcceptanceResult("rejected", "invalid_attempt_id")
            att = _one(
                cur,
                "SELECT *, id::text AS id_text, tenant_id::text AS tenant_text, alert_id::text AS alert_text "
                "FROM tia_investigation_attempts WHERE id = %s::uuid FOR UPDATE;",
                (attempt_uuid,),
            )
            if not att:
                _log(cur, source=source, decision="rejected", reason="unknown_attempt", attempt_id=attempt_uuid)
                return AcceptanceResult("rejected", "unknown_attempt", attempt_id=attempt_uuid)
            tenant_id, alert_id = att["tenant_text"], att["alert_text"]

            mismatch = _binding_mismatch(
                att, claimed_tenant_id, claimed_alert_id, claimed_job_id, claimed_evidence_version
            )
            if mismatch:
                _log(cur, source=source, decision="rejected", reason=mismatch, tenant_id=tenant_id, alert_id=alert_id, attempt_id=attempt_uuid)
                return AcceptanceResult("rejected", mismatch, attempt_id=attempt_uuid)

            alert = _lock_alert(cur, alert_id, tenant_id)
            if not alert:
                _log(cur, source=source, decision="rejected", reason="alert_missing", tenant_id=tenant_id, alert_id=alert_id, attempt_id=attempt_uuid)
                return AcceptanceResult("rejected", "alert_missing", attempt_id=attempt_uuid)

            outcome = tia.normalize_agent_result(raw, source=f"agent_{source}", source_severity=alert["severity"])
            phash = payload_hash(outcome)

            existing = _one(
                cur,
                "SELECT id::text AS id, payload_hash, applied, material, execution_status FROM tia_results WHERE attempt_id = %s::uuid;",
                (attempt_uuid,),
            )
            if existing:
                if existing["payload_hash"] == phash:
                    _log(cur, source=source, decision="duplicate", reason="same_result", tenant_id=tenant_id, alert_id=alert_id, attempt_id=attempt_uuid, phash=phash)
                    return AcceptanceResult(
                        "duplicate", "same_result", attempt_id=attempt_uuid, result_id=existing["id"],
                        applied=bool(existing["applied"]), material=bool(existing["material"]),
                    )
                _log(cur, source=source, decision="conflict", reason="different_payload_for_same_result", tenant_id=tenant_id, alert_id=alert_id, attempt_id=attempt_uuid, phash=phash)
                logger.error("TIA conflicting result rejected attempt=%s", attempt_uuid)
                return AcceptanceResult("conflict", "different_payload_for_same_result", attempt_id=attempt_uuid, result_id=existing["id"])

            expired = _one(cur, "SELECT (now() > %s::timestamptz) AS expired;", (att["accept_until"],))
            if expired and expired["expired"]:
                _log(cur, source=source, decision="rejected", reason="attempt_window_expired", tenant_id=tenant_id, alert_id=alert_id, attempt_id=attempt_uuid, phash=phash)
                return AcceptanceResult("rejected", "attempt_window_expired", attempt_id=attempt_uuid)

            return _accept(
                cur, source=source, att=att, alert=alert, outcome=outcome, phash=phash, fallback=fallback
            )
    except tia_schema.SchemaNotReady:
        raise
    except Exception:
        # Roll back and let the caller keep the work. Never report success.
        tia_schema.reset_cache()
        raise


def accept_local_triage(*, alert_id: str, tenant_id: str, triage: Dict[str, Any]) -> AcceptanceResult:
    """Route the local (Ollama Tier-1) analysis through the same acceptance logic.

    Used only when the agent path is not the primary investigator. The Tier-1
    engine has already stored its own analysis fields; this records the attempt,
    the result with provenance, and applies the same review/escalation policy.
    A non-succeeded local result is a degraded failure, never a verdict.
    """
    att = open_attempt(alert_id=alert_id, tenant_id=tenant_id)
    verdict = {"MALICIOUS": "Critical", "SUSPICIOUS": "Suspicious", "BENIGN_FALSE_POSITIVE": "Benign"}.get(
        str(triage.get("verdict") or "")
    )
    model = f"ollama:{triage.get('model') or 'unknown'}"
    with db_transaction() as cur:
        locked = _lock_alert(cur, alert_id, tenant_id)
        if not locked:
            return AcceptanceResult("rejected", "alert_missing", attempt_id=att["attempt_id"])
        attempt = _one(
            cur,
            "SELECT *, id::text AS id_text, tenant_id::text AS tenant_text, alert_id::text AS alert_text "
            "FROM tia_investigation_attempts WHERE id = %s::uuid FOR UPDATE;",
            (att["attempt_id"],),
        )
        provenance = {"provider": model, "source": "local_tier1", "policy_version": tia.POLICY_VERSION}
        if triage.get("execution_status") == "succeeded" and verdict and triage.get("confidence") is not None:
            outcome = tia.Outcome(
                execution_status="succeeded",
                disposition="malicious" if verdict == "Critical" else "inconclusive",
                llm={"verdict": verdict, "confidence": float(triage["confidence"]),
                     "summary": str(triage.get("summary") or "")[:4000], "action_package": {}},
                verdict_db=str(triage.get("verdict")),
                confidence=float(triage["confidence"]),
                source_severity=locked["severity"],
                provenance=provenance,
            )
        else:
            outcome = tia._failure(
                "degraded", "fallback_rule_based", provenance=provenance, source_severity=locked["severity"],
                limited={"note": "Local analysis was rule-based or incomplete; it is not a conclusion."},
            )
        return _accept(cur, source="local", att=attempt, alert=locked, outcome=outcome,
                       phash=payload_hash(outcome), fallback=None, local=True)


def record_attempt_failure(
    *,
    attempt_id: Any,
    category: str,
    timed_out: bool = False,
    error: Optional[str] = None,
    fallback: Optional[Dict[str, Any]] = None,
) -> AcceptanceResult:
    """A failure the control plane observed itself (timeout, unreachable agent).

    This is NOT an agent result, so it never occupies the attempt's immutable
    result slot: a late callback for the same attempt is still accepted. A
    timeout marks the outcome uncertain; the remote work may still finish.
    """
    tia_schema.require_schema()
    attempt_uuid = _valid_uuid(attempt_id)
    if not attempt_uuid:
        return AcceptanceResult("rejected", "invalid_attempt_id")
    with db_transaction() as cur:
        att = _one(
            cur,
            "SELECT *, id::text AS id_text, tenant_id::text AS tenant_text, alert_id::text AS alert_text "
            "FROM tia_investigation_attempts WHERE id = %s::uuid FOR UPDATE;",
            (attempt_uuid,),
        )
        if not att:
            _log(cur, source="control_plane", decision="rejected", reason="unknown_attempt", attempt_id=attempt_uuid)
            return AcceptanceResult("rejected", "unknown_attempt", attempt_id=attempt_uuid)
        if att["status"] != "dispatched":
            # Already settled by a result or an earlier failure record: idempotent.
            _log(cur, source="control_plane", decision="duplicate", reason=f"attempt_{att['status']}", tenant_id=att["tenant_text"], alert_id=att["alert_text"], attempt_id=attempt_uuid)
            return AcceptanceResult("duplicate", f"attempt_{att['status']}", attempt_id=attempt_uuid)
        alert = _lock_alert(cur, att["alert_text"], att["tenant_text"])
        if not alert:
            return AcceptanceResult("rejected", "alert_missing", attempt_id=attempt_uuid)
        outcome = tia.transport_failure(category, timed_out=timed_out, error=error, source_severity=alert["severity"])
        status = "timed_out" if timed_out else "transport_failed"
        cur.execute(
            """
            UPDATE tia_investigation_attempts
            SET status = %s, outcome_uncertain = %s, transport_error = %s, closed_at = now()
            WHERE id = %s::uuid;
            """,
            (status, bool(timed_out), (error or category)[:200], attempt_uuid),
        )
        if timed_out:
            outcome.limited_evidence = {
                **(outcome.limited_evidence or {}),
                "uncertainty": "HTTP timeout does not prove the remote investigation stopped; a late result will still be accepted.",
            }
        decision, extra = _decide(alert, outcome, fallback)
        if _newer_settled_result(cur, att, alert["id"]):
            _log(cur, source="control_plane", decision="accepted", reason="superseded_failure_history_only", tenant_id=att["tenant_text"], alert_id=att["alert_text"], attempt_id=attempt_uuid)
            return AcceptanceResult("accepted", "superseded_failure_history_only", attempt_id=attempt_uuid, decision=decision, outcome=outcome)
        policy = _apply_policy(cur, att=att, alert=alert, outcome=outcome, decision=decision, surfaced=False, extra=extra)
        _log(cur, source="control_plane", decision="accepted", reason=status, tenant_id=att["tenant_text"], alert_id=att["alert_text"], attempt_id=attempt_uuid)
        return AcceptanceResult(
            "accepted", status, attempt_id=attempt_uuid, decision=decision, outcome=outcome,
            review_item_id=policy["review_item_id"], review_action=policy["review_action"],
            notification_ids=policy["notification_ids"],
        )


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------


def _binding_mismatch(att, tenant, alert, job, version) -> Optional[str]:
    if tenant is not None and str(tenant) != att["tenant_text"]:
        return "tenant_mismatch"
    if alert is not None and str(alert) != att["alert_text"]:
        return "alert_mismatch"
    if job is not None and str(job) != att["job_key"]:
        return "job_mismatch"
    if version is not None and str(version) != att["evidence_version"]:
        return "evidence_version_mismatch"
    return None


def _decide(alert: Dict[str, Any], outcome: tia.Outcome, fallback: Optional[Dict[str, Any]]):
    """Policy decision and the evidence that goes with it."""
    extra: Dict[str, Any] = {}
    from app.services.soc_agent_expert import outcome_to_triage

    triage = outcome_to_triage(outcome)
    if not outcome.succeeded and fallback is not None:
        extra["fallback_triage"] = {
            "model": fallback.get("model"),
            "evidence_basis": fallback.get("evidence_basis"),
            "verdict": fallback.get("verdict"),
            "confidence": fallback.get("confidence"),
            "summary": str(fallback.get("summary") or "")[:500],
            "note": "Secondary path after the primary investigation failed. Not a conclusion.",
        }
        decision_input = {**fallback, "execution_status": "degraded", "error_category": outcome.error_category}
    else:
        decision_input = triage
    decision = tia.decide_review(
        source_severity=alert.get("severity"),
        asset_criticality=alert.get("asset_criticality"),
        execution_status=str(decision_input.get("execution_status") or "degraded"),
        error_category=decision_input.get("error_category") or outcome.error_category,
        verdict=decision_input.get("verdict"),
        confidence=decision_input.get("confidence") or 0.0,
        recommended_action=decision_input.get("recommended_action"),
        model_review_requested=bool(decision_input.get("model_review_requested")),
        escalate_floor=tia.escalate_floor(),
        benign_silence_floor=tia.benign_silence_floor(),
    )
    if not outcome.succeeded and fallback is not None:
        decision["execution_status"] = "degraded"
    elif not outcome.succeeded:
        decision["execution_status"] = outcome.execution_status
    decision["error_category"] = outcome.error_category
    return decision, extra


def _newer_settled_result(cur, att, alert_id: str) -> bool:
    row = _one(
        cur,
        """
        SELECT 1 AS hit
        FROM tia_results r
        JOIN tia_investigation_attempts a ON a.id = r.attempt_id
        WHERE r.alert_id = %s::uuid
          AND a.evidence_version = %s
          AND a.attempt_no > %s
          AND (r.applied OR r.execution_status = 'succeeded')
        LIMIT 1;
        """,
        (alert_id, att["evidence_version"], att["attempt_no"]),
    )
    return bool(row)


def _applicability(cur, att, alert, outcome, current_version) -> tuple:
    if not outcome.succeeded:
        if _newer_settled_result(cur, att, alert["id"]):
            return False, "superseded_failure_history_only"
        return False, "no_verdict"
    if att["evidence_version"] != current_version:
        return False, "stale_evidence"
    status = str(alert.get("status") or "").lower()
    triage_status = str(alert.get("ai_triage_status") or "").lower()
    if status in TERMINAL_ALERT_STATUSES or triage_status in HUMAN_TRIAGE_STATUSES:
        return False, "human_decision"
    if _newer_settled_result(cur, att, alert["id"]):
        return False, "superseded_by_newer_attempt"
    return True, "applied"


def _accept(cur, *, source, att, alert, outcome: tia.Outcome, phash: str, fallback, local: bool = False) -> AcceptanceResult:
    from app.services import soc_agent_expert as expert

    tenant_id, alert_id = att["tenant_text"], att["alert_text"]
    current_version = evidence_version(cur, alert_id, tenant_id)
    applied, apply_reason = _applicability(cur, att, alert, outcome, current_version)
    persist = applied
    if local and outcome.succeeded and applied:
        apply_reason = "applied_local"  # the Tier-1 engine already stored its own fields
        persist = False
    late = att["status"] in ("timed_out", "transport_failed")
    decision, extra = _decide(alert, outcome, fallback)
    triage = expert.outcome_to_triage(outcome)

    surfaced = False
    material = False
    if outcome.succeeded and not applied:
        # Kept as history only, but a serious finding must still reach a person.
        material = bool(decision.get("escalate") or outcome.verdict_db == "MALICIOUS")
        surfaced = material

    result_row = _one(
        cur,
        """
        INSERT INTO tia_results
            (attempt_id, tenant_id, alert_id, evidence_version, first_source, payload_hash,
             execution_status, error_category, verdict, confidence, disposition,
             outcome, provenance, applied, apply_reason, material, late)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s::jsonb, %s, %s, %s, %s)
        RETURNING id::text AS id;
        """,
        (
            att["id_text"], tenant_id, alert_id, att["evidence_version"], source, phash,
            outcome.execution_status, outcome.error_category, outcome.verdict_db, outcome.confidence,
            outcome.disposition,
            json.dumps({"llm": outcome.llm, "limited_evidence": outcome.limited_evidence}, default=str),
            json.dumps(outcome.provenance, default=str),
            applied, apply_reason, material, late,
        ),
    )
    cur.execute(
        "UPDATE tia_investigation_attempts SET status = 'result_received', outcome_uncertain = false, "
        "closed_at = COALESCE(closed_at, now()) WHERE id = %s::uuid;",
        (att["id_text"],),
    )

    if persist:
        expert.persist_expert_fields(alert_id=alert_id, tenant_id=tenant_id, triage=triage, cur=cur)
        rec_id = expert.maybe_create_customer_recommendation(
            alert_id=alert_id, tenant_id=tenant_id, triage=triage, cur=cur
        )
        if rec_id:
            triage["recommendation_id"] = rec_id

    policy = {"review_item_id": None, "review_action": None, "notification_ids": []}
    if apply_reason == "superseded_failure_history_only":
        pass
    elif outcome.succeeded and not applied and not surfaced:
        policy["review_action"] = "history_only"
    else:
        policy = _apply_policy(
            cur, att=att, alert=alert, outcome=outcome, decision=decision, surfaced=surfaced, extra=extra,
            force_reason="stale_result_material" if surfaced else None,
        )
    _log(cur, source=source, decision="accepted", reason=apply_reason, tenant_id=tenant_id, alert_id=alert_id, attempt_id=att["id_text"], phash=phash)
    return AcceptanceResult(
        "accepted", apply_reason, attempt_id=att["id_text"], result_id=result_row["id"], applied=applied,
        material=material, late=late, review_item_id=policy["review_item_id"],
        review_action=policy["review_action"], notification_ids=policy["notification_ids"],
        decision=decision, outcome=outcome, triage=triage,
    )


# --------------------------------------------------------------------------
# review lifecycle + notification obligations
# --------------------------------------------------------------------------


def _finding_class(outcome: tia.Outcome) -> str:
    return f"verdict:{outcome.verdict_db}" if outcome.succeeded and outcome.verdict_db else "analysis_unavailable"


def _event(cur, tenant_id, item_id, event_type, *, actor="system", from_status=None, to_status=None, attempt_id=None, detail=None) -> None:
    cur.execute(
        """
        INSERT INTO tia_review_events
            (tenant_id, review_item_id, event_type, actor, from_status, to_status, attempt_id, detail)
        VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s::jsonb);
        """,
        (tenant_id, item_id, event_type, actor, from_status, to_status, attempt_id, json.dumps(detail or {}, default=str)),
    )


def _apply_policy(
    cur, *, att, alert, outcome: tia.Outcome, decision: Dict[str, Any], surfaced: bool, extra: Dict[str, Any],
    force_reason: Optional[str] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"review_item_id": None, "review_action": None, "notification_ids": []}
    required = bool(decision.get("review_required")) or surfaced
    if required:
        if force_reason:
            decision = {**decision, "reason_code": force_reason}
        review = _review_upsert(cur, att=att, alert=alert, outcome=outcome, decision=decision, extra=extra, surfaced=surfaced)
        out["review_item_id"], out["review_action"] = review["id"], review["action"]
    elif outcome.succeeded:
        flagged = _all(
            cur,
            "UPDATE tia_review_items SET analysis_available = true "
            "WHERE alert_id = %s::uuid AND status <> 'resolved' AND analysis_available = false RETURNING id::text AS id;",
            (att["alert_text"],),
        )
        for row in flagged:
            _event(cur, att["tenant_text"], row["id"], "analysis_available", attempt_id=att["id_text"],
                   detail={"verdict": outcome.verdict_db, "confidence": outcome.confidence})
        out["review_action"] = "analysis_available" if flagged else "none"

    if decision.get("escalate"):
        out["notification_ids"] = _enqueue_page(
            cur, att=att, alert=alert, outcome=outcome, decision=decision, review_item_id=out["review_item_id"]
        )
    elif required and not outcome.succeeded:
        out["notification_ids"] = _enqueue_outage_notice(
            cur, att=att, alert=alert, decision=decision, review_item_id=out["review_item_id"]
        )
    if out["review_item_id"]:
        # An arrival page sent before the review item existed belongs to it from now on,
        # so acknowledging or resolving the item settles that page too.
        cur.execute(
            "UPDATE tia_notifications SET review_item_id = %s::uuid WHERE alert_id = %s::uuid AND kind = 'page' AND review_item_id IS NULL;",
            (out["review_item_id"], att["alert_text"]),
        )
        sync_item_notification_state(cur, out["review_item_id"])
    return out


def _review_upsert(cur, *, att, alert, outcome, decision, extra, surfaced) -> Dict[str, Any]:
    tenant_id, alert_id = att["tenant_text"], att["alert_text"]
    due_minutes = int(decision.get("due_minutes") or 60)
    priority = decision.get("assessed_priority") or "P3"
    reason_code = decision.get("reason_code") or "policy_required"
    finding = _finding_class(outcome)
    limited = {**(outcome.limited_evidence or {}), **extra}
    provenance = {**(outcome.provenance or {}), "attempt_id": att["id_text"], "attempt_no": att["attempt_no"]}
    reasons = decision.get("reasons") or []
    page = bool(decision.get("escalate"))
    detail = {"reason_code": reason_code, "priority": priority, "finding": finding, "execution_status": decision.get("execution_status")}

    live = _one(
        cur,
        "SELECT * FROM tia_review_items WHERE alert_id = %s::uuid AND status <> 'resolved' FOR UPDATE;",
        (alert_id,),
    )
    if live:
        rose = priority < (live["assessed_priority"] or "P4")
        higher_finding = _FINDING_RANK.get(finding, 0) > _FINDING_RANK.get(live.get("highest_finding") or "", -1)
        cur.execute(
            """
            UPDATE tia_review_items SET
                occurrences = occurrences + 1,
                last_seen_at = now(),
                -- an acknowledged item goes back to open only for a higher priority or a more serious finding
                status = CASE WHEN status = 'acknowledged' AND %s THEN 'open' ELSE status END,
                reason_code = %s,
                execution_status = %s,
                error_category = %s,
                assessed_priority = LEAST(assessed_priority, %s),
                notify_urgency = CASE WHEN notify_urgency = 'page' OR %s THEN 'page' ELSE 'queue' END,
                -- deadlines only ever move earlier; age (first_seen_at) never resets
                due_at = LEAST(due_at, now() + make_interval(mins => %s)),
                model_review_requested = model_review_requested OR %s,
                provenance = %s::jsonb,
                limited_evidence = %s::jsonb,
                reasons = %s::jsonb,
                evidence_version = %s,
                highest_finding = CASE WHEN %s THEN %s ELSE highest_finding END
            WHERE id = %s::uuid;
            """,
            (
                bool(rose or higher_finding),
                reason_code, decision.get("execution_status") or "failed", decision.get("error_category"),
                priority, page, due_minutes, bool(outcome.model_review_requested),
                json.dumps(provenance, default=str), json.dumps(limited, default=str)[:20000],
                json.dumps(reasons), att["evidence_version"], higher_finding, finding, live["id"],
            ),
        )
        back_to_open = live["status"] == "acknowledged" and bool(rose or higher_finding)
        _event(cur, tenant_id, str(live["id"]), "priority_raised" if rose else "recurred",
               from_status=live["status"], to_status="open" if back_to_open else live["status"],
               attempt_id=att["id_text"], detail=detail)
        return {"id": str(live["id"]), "action": "priority_raised" if rose else "recurred"}

    last = _one(
        cur,
        "SELECT * FROM tia_review_items WHERE alert_id = %s::uuid ORDER BY resolved_at DESC NULLS LAST, first_seen_at DESC LIMIT 1 FOR UPDATE;",
        (alert_id,),
    )
    if last:
        # last is resolved here (a live item would have matched above)
        new_evidence = bool(last.get("evidence_version")) and last["evidence_version"] != att["evidence_version"]
        material = surfaced or page or outcome.verdict_db == "MALICIOUS" or new_evidence
        if not material:
            _event(cur, tenant_id, str(last["id"]), "recurrence_suppressed", from_status="resolved", to_status="resolved",
                   attempt_id=att["id_text"], detail=detail)
            return {"id": str(last["id"]), "action": "recurrence_suppressed"}
        cur.execute(
            """
            UPDATE tia_review_items SET
                status = 'open', reopened_count = reopened_count + 1, reopened_at = now(),
                resolved_at = NULL, resolved_by = NULL, acknowledged_at = NULL,
                occurrences = occurrences + 1, last_seen_at = now(),
                reason_code = %s, execution_status = %s, error_category = %s,
                assessed_priority = %s,
                notify_urgency = CASE WHEN %s THEN 'page' ELSE 'queue' END,
                due_at = now() + make_interval(mins => %s),
                model_review_requested = %s, analysis_available = false,
                provenance = %s::jsonb, limited_evidence = %s::jsonb, reasons = %s::jsonb,
                evidence_version = %s, highest_finding = %s
            WHERE id = %s::uuid;
            """,
            (
                reason_code, decision.get("execution_status") or "failed", decision.get("error_category"),
                priority, page, due_minutes, bool(outcome.model_review_requested),
                json.dumps(provenance, default=str), json.dumps(limited, default=str)[:20000],
                json.dumps(reasons), att["evidence_version"], finding, last["id"],
            ),
        )
        _event(cur, tenant_id, str(last["id"]), "reopened", from_status="resolved", to_status="open",
               actor="system", attempt_id=att["id_text"], detail={**detail, "new_evidence": new_evidence})
        return {"id": str(last["id"]), "action": "reopened"}

    row = _one(
        cur,
        """
        INSERT INTO tia_review_items (
            tenant_id, alert_id, reason_code, execution_status, error_category,
            source_severity, assessed_priority, notify_urgency, due_at,
            model_review_requested, provenance, limited_evidence, reasons,
            evidence_version, highest_finding, deadline_basis
        )
        VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, now() + make_interval(mins => %s),
                %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, 'provisional')
        RETURNING id::text AS id;
        """,
        (
            tenant_id, alert_id, reason_code, decision.get("execution_status") or "failed",
            decision.get("error_category"), decision.get("source_severity"), priority,
            "page" if page else "queue", due_minutes, bool(outcome.model_review_requested),
            json.dumps(provenance, default=str), json.dumps(limited, default=str)[:20000],
            json.dumps(reasons), att["evidence_version"], finding,
        ),
    )
    _event(cur, tenant_id, row["id"], "created", to_status="open", attempt_id=att["id_text"], detail=detail)
    return {"id": row["id"], "action": "created"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _insert_notifications(
    cur, *, att, alert, kind: str, level: int, base_key: str, roster: List[Dict[str, str]], channel: str,
    body: str, review_item_id: Optional[str], ack_minutes: Optional[int], blocked_reason: str,
) -> List[str]:
    """Insert one outbox row per recipient (or one visible blocked row). Idempotent."""
    if _one(cur, "SELECT 1 AS hit FROM tia_notifications WHERE base_key = %s LIMIT 1;", (base_key,)):
        return []
    ids: List[str] = []
    targets: List[Optional[Dict[str, str]]] = list(roster) if roster else [None]
    for person in targets:
        address = person["address"] if person else None
        key = f"{base_key}:{_sha(address)[:12] if address else 'unassigned'}"
        row = _one(
            cur,
            """
            INSERT INTO tia_notifications
                (tenant_id, alert_id, review_item_id, kind, level, base_key, idempotency_key, channel,
                 recipient_address, recipient_name, message_body, state, blocked_reason,
                 max_attempts, ack_due_at)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'required', %s, %s,
                    CASE WHEN %s::int IS NULL THEN NULL ELSE now() + make_interval(mins => %s::int) END)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id::text AS id;
            """,
            (
                att["tenant_text"], att["alert_text"], review_item_id, kind, level, base_key, key, channel,
                address, person["name"] if person else None, body,
                None if person else blocked_reason,
                _int_env("TIA_NOTIFY_MAX_ATTEMPTS", 4, 1, 20),
                ack_minutes, ack_minutes,
            ),
        )
        if row:
            ids.append(row["id"])
    return ids


def _page_body(alert: Dict[str, Any], outcome: tia.Outcome, decision: Dict[str, Any]) -> str:
    from app.services.ai_deep_triage import build_escalation_message

    view = {
        "id": alert.get("id"),
        "severity": alert.get("severity"),
        "tenant_name": alert.get("tenant_name"),
        "short_code": alert.get("short_code"),
        "asset_hostname": alert.get("asset_hostname"),
        "destination_host": alert.get("destination_host"),
        "alert_title": alert.get("alert_title"),
        "ai_plain_summary": (outcome.llm or {}).get("summary") if outcome.succeeded else None,
    }
    return build_escalation_message(view, decision)


def _enqueue_page(cur, *, att, alert, outcome, decision, review_item_id, level: int = 1) -> List[str]:
    finding = _finding_class(outcome)
    priority = decision.get("assessed_priority") or "P3"
    # Identity of "the same page": alert + priority + kind of finding + evidence.
    # A duplicate result maps to the same key. A higher priority, a different kind
    # of finding (a late MALICIOUS after an unavailable-analysis page), or new
    # evidence maps to a new key and so produces its own notification.
    base = _sha(f"page|{att['alert_text']}|{priority}|{finding}|{att['evidence_version']}|L{level}")
    from app.services import tia_schema as cfg

    return _insert_notifications(
        cur, att=att, alert=alert, kind="page", level=level, base_key=base,
        roster=cfg.oncall_roster() if level == 1 else cfg.escalation_roster(),
        channel=cfg.escalation_channel(), body=_page_body(alert, outcome, decision),
        review_item_id=review_item_id, ack_minutes=page_ack_minutes(),
        blocked_reason="no_recipients_configured" if level == 1 else "escalation_target_not_configured",
    )


def page_on_intake_enabled() -> bool:
    """Off until the on-call rota agrees to the extra page (arrival page + findings page)."""
    return (os.getenv("TIA_PAGE_ON_INTAKE") or "").strip().lower() in ("1", "true", "yes")


def urgent_on_intake(alert: Dict[str, Any]) -> bool:
    """Page before the investigation finishes: a critical detection, or a high one on a critical asset."""
    if not page_on_intake_enabled():
        return False
    sev = str(alert.get("severity") or "").lower()
    crit = str(alert.get("asset_criticality") or "").lower()
    return sev == "critical" or (sev == "high" and crit == "critical")


def _enqueue_intake_page(cur, *, alert: Dict[str, Any], version: str) -> List[str]:
    """One page per alert and evidence version, sent while TIA is still investigating.

    The result page that follows has a different key (it carries a finding), so the
    analyst gets the analysis too; a retry of the same attempt maps to this same key.
    """
    from app.services import tia_schema as cfg

    att = {"tenant_text": alert["tenant_id"], "alert_text": alert["id"]}
    host = alert.get("asset_hostname") or alert.get("destination_host") or "unknown host"
    body = (
        f"[{str(alert.get('severity') or '').upper()}] Kevantic SOC - {alert.get('tenant_name') or alert.get('short_code')}\n"
        f"Host: {host}\n{(alert.get('alert_title') or '')[:300]}\n\n"
        "Paged on arrival. TIA's investigation is still running; its findings follow separately. "
        "Nothing has been concluded or contained.\n"
        f"Alert ID: {alert['id']}"
    )
    return _insert_notifications(
        cur, att=att, alert=alert, kind="page", level=1,
        base_key=_sha(f"page|{alert['id']}|intake|{version}|L1"),
        roster=cfg.oncall_roster(), channel=cfg.escalation_channel(), body=body,
        review_item_id=None, ack_minutes=page_ack_minutes(), blocked_reason="no_recipients_configured",
    )


def _enqueue_outage_notice(cur, *, att, alert, decision, review_item_id) -> List[str]:
    category = decision.get("error_category")
    if category not in tia.PROVIDER_WIDE_CATEGORIES:
        return []
    bucket = int(time.time() // outage_window_seconds())
    base = _sha(f"outage|{category}|{bucket}")
    from app.services import tia_schema as cfg

    body = (
        f"[TIA] Investigation provider failure ({category}). Affected cases are queued for "
        "analyst review in the SOC console. This notice is sent once per window, not once per case."
    )
    return _insert_notifications(
        cur, att=att, alert=alert, kind="outage_notice", level=1, base_key=base,
        roster=cfg.oncall_roster(), channel=cfg.escalation_channel(), body=body,
        review_item_id=review_item_id, ack_minutes=None, blocked_reason="no_recipients_configured",
    )


_ITEM_STATE_FOR = {
    "required": "page_required",
    "queued": "page_queued",
    "submitted": "page_submitted",
    "delivered": "page_delivered",
    "failed": "page_failed",
    "acknowledged": "acknowledged",
}


def sync_item_notification_state(cur, review_item_id: str) -> str:
    """Summarise the item's page rows into review_items.notification_state."""
    rows = _all(
        cur,
        "SELECT state, recipient_address, blocked_reason FROM tia_notifications "
        "WHERE review_item_id = %s::uuid AND kind = 'page' AND state <> 'cancelled';",
        (review_item_id,),
    )
    if not rows:
        state = "not_required"
    elif any(r["state"] == "acknowledged" for r in rows):
        state = "acknowledged"
    elif any(r["recipient_address"] is None and r["state"] in ("required", "queued") for r in rows):
        state = "no_recipients_configured"
    else:
        order = ["delivered", "submitted", "queued", "required", "failed"]
        best = next((s for s in order if any(r["state"] == s for r in rows)), "required")
        state = _ITEM_STATE_FOR.get(best, "page_required")
    cur.execute("UPDATE tia_review_items SET notification_state = %s WHERE id = %s::uuid;", (state, review_item_id))
    return state
