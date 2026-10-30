"""KB-116: Autonomous deep triage + human escalation decision.

Stage 3 of the AI alert pipeline, after KB-092 (plain-English explain) and
KB-096 (SOC triage assist). Those two stages describe an alert. This stage
runs the full Tier-1 enrichment engine (`ai_tier1_triage.run_tier1_triage`)
on every qualifying alert instead of waiting for an analyst to open it, then
decides whether a human must be woken now.

Design rules:
  - Escalation is deterministic, not LLM-decided. The model supplies a verdict;
    fixed thresholds decide whether that verdict wakes a person.
  - Fail toward the human. When the model is unavailable and the alert is
    severe, escalate rather than stay silent.
  - Never auto-execute containment. This stage raises people; it does not act.
    Containment remains human-approved via the existing EDR paths.
  - Every result, from the HTTP reply or the callback, goes through ONE function,
    tia_acceptance.accept_result, which records it, applies the review/escalation
    policy and queues notifications in a single transaction.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from app.db.session import fetch_one
from app.services import tia_acceptance as acc
from app.services import tia_investigation as tia
from app.services import tia_outbox
from app.services import tia_schema
from app.services.ai_tier1_triage import run_tier1_triage
from app.services.soc_alert_taxonomy import enrich_alert_row

logger = logging.getLogger(__name__)

_SEVERITY_RANKS = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_CRITICAL_ASSET_TIERS = ("critical", "high")


def deep_triage_enabled() -> bool:
    return (os.getenv("AI_DEEP_TRIAGE_ENABLED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _min_severity_rank() -> int:
    raw = (os.getenv("AI_DEEP_TRIAGE_MIN_SEVERITY") or "high").strip().lower()
    return _SEVERITY_RANKS.get(raw, 3)


def _severity_ok(severity: Optional[str]) -> bool:
    rank = _SEVERITY_RANKS.get((severity or "").strip().lower(), 0)
    return rank >= _min_severity_rank()


def _escalate_confidence_floor() -> float:
    """Confidence floor for waking a human, on the engine's 0-100 scale.

    Matches ai_tier1_triage, where confidence is schema-bound to 0..100
    (LOW_PRIORITY_CONFIDENCE_MIN = 85.0, AUTO_CLOSE_CONFIDENCE_MIN = 95.0).
    """
    try:
        return float(os.getenv("AI_DEEP_TRIAGE_ESCALATE_CONFIDENCE") or "60")
    except ValueError:
        return 60.0


def _benign_silence_confidence() -> float:
    """A BENIGN verdict on a critical alert stays silent only at or above this.

    Default matches ai_tier1_triage LOW_PRIORITY_CONFIDENCE_MIN (85.0).
    """
    try:
        return float(os.getenv("AI_DEEP_TRIAGE_BENIGN_SILENCE_CONFIDENCE") or "85")
    except ValueError:
        return 85.0


def _llm_timeout_seconds() -> float:
    """Background budget for the model call.

    The dashboard path keeps its 8s budget; this stage runs off the request path
    and may queue behind KB-092/KB-096 calls on a single-slot CPU Ollama.
    """
    try:
        val = float(os.getenv("AI_DEEP_TRIAGE_TIMEOUT_SECONDS") or "180")
    except ValueError:
        val = 180.0
    return max(10.0, min(val, 600.0))


def load_alert_for_triage(alert_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """Load the same enriched alert shape the on-demand triage endpoint uses.

    Mirrors `_alert_detail` in api/routes/alert_incident_triage.py. Kept here so
    the worker never imports from the API layer.
    """
    alert = fetch_one(
        """
        SELECT
            sa.id::text,
            sa.tenant_id::text,
            t.name AS tenant_name,
            t.short_code,
            sa.appliance_id::text,
            a.appliance_name,
            sa.asset_id::text,
            pa.hostname AS asset_hostname,
            pa.asset_type AS asset_type,
            pa.os_name AS asset_os_name,
            CASE WHEN pa.ip_address IS NOT NULL THEN host(pa.ip_address)::text ELSE NULL END AS asset_ip,
            pa.criticality AS asset_criticality,
            pa.owner AS asset_owner,
            pa.details AS asset_details,
            t.timezone AS tenant_timezone,
            sa.source_tool,
            sa.external_alert_id,
            sa.severity,
            sa.alert_title,
            sa.alert_description,
            sa.event_time,
            CASE WHEN sa.source_ip IS NOT NULL THEN host(sa.source_ip)::text ELSE NULL END AS source_ip,
            CASE WHEN sa.destination_ip IS NOT NULL THEN host(sa.destination_ip)::text ELSE NULL END AS destination_ip,
            sa.source_user,
            sa.destination_host,
            sa.raw_event,
            sa.win_eventdata,
            sa.wazuh_full_log,
            sa.parent_process,
            sa.parent_command_line,
            sa.current_directory,
            sa.integrity_level,
            sa.process_guid,
            sa.parent_process_guid,
            sa.logon_id,
            sa.logon_guid,
            sa.hashes_raw,
            sa.hash_md5,
            sa.hash_sha256,
            sa.hash_imphash,
            sa.process_id,
            sa.parent_process_id,
            sa.user_sid,
            sa.ai_plain_summary,
            sa.ai_technical_summary,
            sa.ai_likely_attack_type,
            sa.ai_business_impact,
            sa.ai_recommended_action,
            sa.ai_false_positive_score,
            sa.ai_risk_score,
            sa.ai_risk_rationale,
            sa.ai_enrichment_notes,
            sa.ai_correlation_notes,
            sa.ai_containment_suggestion,
            sa.ai_triage_status,
            sa.ai_triaged_at,
            sa.ai_verdict,
            sa.ai_confidence,
            sa.ai_queue,
            sa.ai_auto_closed,
            sa.ai_resolution_label,
            sa.mitre_mapping,
            sa.customer_visible,
            sa.status,
            sa.created_at,
            sa.updated_at
        FROM security_alerts sa
        JOIN tenants t ON t.id = sa.tenant_id
        LEFT JOIN appliances a ON a.id = sa.appliance_id
        LEFT JOIN protected_assets pa ON pa.id = sa.asset_id
        WHERE sa.id = %s::uuid AND sa.tenant_id = %s::uuid
        LIMIT 1;
        """,
        (alert_id, tenant_id),
    )
    if not alert:
        return None
    return enrich_alert_row(alert)


def decide_escalation(
    alert: Dict[str, Any],
    triage: Dict[str, Any],
) -> Dict[str, Any]:
    """Decide whether this alert needs a person, and whether to wake one.

    Fixed rules only (tia_investigation.decide_review). Degradation is read from
    the explicit ``execution_status`` on the triage, never from the model name; a
    triage without one is treated as degraded (fail toward the human).

    Returns {"escalate": bool, "review_required": bool, "urgency": str,
    "reasons": [str], ...}. ``escalate`` means page; ``review_required`` means a
    durable analyst review item.
    """
    return tia.decide_review(
        source_severity=alert.get("severity"),
        asset_criticality=alert.get("asset_criticality"),
        execution_status=str(triage.get("execution_status") or "degraded"),
        error_category=triage.get("error_category"),
        verdict=triage.get("verdict"),
        confidence=triage.get("confidence") or 0.0,
        recommended_action=triage.get("recommended_action"),
        model_review_requested=bool(triage.get("model_review_requested")),
        escalate_floor=_escalate_confidence_floor(),
        benign_silence_floor=_benign_silence_confidence(),
    )


def build_escalation_message(alert: Dict[str, Any], decision: Dict[str, Any]) -> str:
    """Human-readable page body. Carries the analysis, not just a wake-up ping."""
    host = alert.get("asset_hostname") or alert.get("destination_host") or "unknown host"
    tenant = alert.get("tenant_name") or alert.get("short_code") or "unknown tenant"
    severity = (alert.get("severity") or "unknown").upper()
    verdict = decision.get("verdict")
    confidence = decision.get("confidence") or 0.0
    summary = (alert.get("ai_plain_summary") or alert.get("alert_title") or "").strip()
    action = decision.get("recommended_action") or "INVESTIGATE_HOST"
    reasons = "; ".join(decision.get("reasons") or []) or "escalation rules matched"

    lines = [
        f"[{severity}] Kevantic SOC escalation — {tenant}",
        f"Host: {host}",
        (
            f"AI verdict: {verdict} ({confidence:.0f}% confidence)"
            if verdict
            else f"AI investigation: {decision.get('execution_status', 'unavailable').replace('_', ' ').upper()}"
            f" ({decision.get('error_category') or 'no analysis'}) — no verdict"
        ),
        f"Suggested next step: {action}",
        (
            f"Review target: {decision.get('due_minutes')} minutes (provisional, not an approved customer SLA)"
            if decision.get("due_minutes")
            else None
        ),
        "",
        summary[:600],
        "",
        f"Why you were paged: {reasons}",
        f"Alert ID: {alert.get('id')}",
    ]
    return "\n".join(line for line in lines if line is not None)


def record_dead_letter_review(*, alert_id: str, tenant_id: str, attempts: int) -> None:
    """Last-resort durable record when a job exhausts its retries.

    Called by the queue when it dead-letters a job for a reason other than a
    missing schema, so the case shows up in the analyst review queue even if every
    earlier attempt crashed before routing.
    """
    binding = acc.open_attempt(alert_id=alert_id, tenant_id=tenant_id)
    acc.record_attempt_failure(
        attempt_id=binding["attempt_id"],
        category="unexpected_error",
        error=f"job exhausted {attempts} attempts",
    )
    tia_outbox.kick()


def _manual_review(alert_id: str, tenant_id: str) -> bool:
    """Rollback / safe mode: no model call; the case goes to an analyst."""
    binding = acc.open_attempt(alert_id=alert_id, tenant_id=tenant_id)
    res = acc.record_attempt_failure(
        attempt_id=binding["attempt_id"],
        category="manual_review_mode",
        error="TIA_INVESTIGATION_MODE=manual_review",
    )
    tia_outbox.kick()
    return res.handled


def process_deep_triage_job(*, alert_id: str, tenant_id: str) -> bool:
    """Investigate one alert (Cursor SOC agent and/or local Tier-1) and accept the result.

    Returns True when the case has been handled durably (analysis stored, or a
    review item recorded). Returns False only when a retry may help (transient
    infrastructure failure); the queue bounds retries and dead-letters. Raises
    SchemaNotReady / a database error when nothing could be recorded, so the queue
    keeps the job instead of acknowledging it. Never auto-contains.
    """
    from app.services.soc_agent_client import soc_agent_enabled, severity_meets_agent_threshold

    agent_on = soc_agent_enabled()
    if not deep_triage_enabled() and not agent_on:
        return False

    alert = load_alert_for_triage(alert_id, tenant_id)
    if not alert:
        logger.info("Deep triage skipped — alert not found id=%s", alert_id)
        return False

    severity_ok = bool(agent_on and severity_meets_agent_threshold(alert.get("severity")))
    if deep_triage_enabled() and _severity_ok(alert.get("severity")):
        severity_ok = True
    if not severity_ok:
        return False

    if (alert.get("ai_triage_status") or "").strip() == "accepted":
        return True

    # Work that depends on the new tables is never started without them.
    tia_schema.require_schema()

    if tia.investigation_mode() == "manual_review":
        return _manual_review(alert_id, tenant_id)

    if agent_on and severity_meets_agent_threshold(alert.get("severity")):
        return _investigate_with_agent(alert=alert, alert_id=alert_id, tenant_id=tenant_id)

    triage = _run_ollama(alert_id=alert_id, tenant_id=tenant_id, alert=alert, limited=False)
    if triage is None:
        return False
    res = acc.accept_local_triage(alert_id=alert_id, tenant_id=tenant_id, triage=triage)
    tia_outbox.kick()
    logger.info(
        "Local deep triage accepted id=%s status=%s review=%s action=%s",
        alert_id, res.status, res.review_item_id, res.review_action,
    )
    return res.handled


_TRANSIENT_CATEGORIES = ("timeout", "agent_unreachable", "agent_http_error")


def _investigate_with_agent(*, alert: Dict[str, Any], alert_id: str, tenant_id: str) -> bool:
    from app.services.soc_agent_client import AgentCallError, call_agent_ingest

    binding = acc.open_attempt(alert_id=alert_id, tenant_id=tenant_id)
    attempt_id = binding["attempt_id"]
    alert = _with_evidence(alert, alert_id=alert_id, tenant_id=tenant_id, attempt_id=attempt_id)
    try:
        raw = call_agent_ingest(alert, binding)
    except AgentCallError as exc:
        logger.warning("SOC agent call failed id=%s category=%s attempt=%s", alert_id, exc.category, attempt_id)
        fallback = (
            _run_ollama(alert_id=alert_id, tenant_id=tenant_id, alert=alert, limited=True)
            if deep_triage_enabled()
            else None
        )
        res = acc.record_attempt_failure(
            attempt_id=attempt_id, category=exc.category, timed_out=exc.timed_out,
            error=exc.detail or None, fallback=fallback,
        )
        tia_outbox.kick()
        _ticket_note(attempt_id)
        logger.warning(
            "Investigation not completed id=%s category=%s review_item=%s", alert_id, exc.category, res.review_item_id
        )
        # Retry only transient infrastructure failures. The review item is already
        # durable, so a retry never loses the case; the queue bounds attempts.
        return res.handled and exc.category not in _TRANSIENT_CATEGORIES

    echo = raw.get("tia_binding") if isinstance(raw.get("tia_binding"), dict) else {}
    probe = tia.normalize_agent_result(raw, source="agent_http", source_severity=alert.get("severity"))
    fallback = (
        _run_ollama(alert_id=alert_id, tenant_id=tenant_id, alert=alert, limited=True)
        if (not probe.succeeded and deep_triage_enabled())
        else None
    )
    res = acc.accept_result(
        source="http",
        attempt_id=attempt_id,
        claimed_tenant_id=echo.get("tenant_id"),
        claimed_alert_id=echo.get("alert_id"),
        claimed_job_id=echo.get("job_id"),
        claimed_evidence_version=echo.get("evidence_version"),
        raw=raw,
        fallback=fallback,
    )
    if not res.handled:
        # A reply that does not belong to this attempt is a failed investigation,
        # not an accepted one. The attempt is still open, so the case is kept.
        logger.error("Agent reply rejected id=%s reason=%s attempt=%s", alert_id, res.reason, attempt_id)
        res = acc.record_attempt_failure(attempt_id=attempt_id, category="invalid_agent_result", error=res.reason)
    tia_outbox.kick()
    _ticket_note(attempt_id)
    logger.info(
        "Investigation accepted id=%s status=%s reason=%s review_item=%s action=%s",
        alert_id, res.status, res.reason, res.review_item_id, res.review_action,
    )
    return res.handled and probe.error_category not in _TRANSIENT_CATEGORIES


def _ticket_note(attempt_id: str) -> None:
    from app.services import tia_ticket_note

    note = tia_ticket_note.after_acceptance(attempt_id)
    if note:
        logger.info("ticket note attempt=%s outcome=%s", attempt_id, note.get("outcome"))


def _with_evidence(alert: Dict[str, Any], *, alert_id: str, tenant_id: str, attempt_id: str) -> Dict[str, Any]:
    """Attach the dossier (full or redacted, per the tenant's grant) and record what was sent."""
    from app.services import tia_evidence, tia_research_policy

    out = dict(alert)
    out["tia_research_policy"] = tia_research_policy.agent_research_policy(tenant_id)
    ev = tia_evidence.for_agent(tenant_id, alert_id)
    if ev is None:
        manifest: Dict[str, Any] = {"dossier_version": tia_evidence.DOSSIER_VERSION, "sent_form": "none", "note": "dossier could not be built"}
    else:
        out["tia_evidence"] = ev["payload"]
        manifest = ev["manifest"]
    manifest["research_policy"] = out["tia_research_policy"]
    try:
        from app.db.session import execute

        execute(
            "UPDATE tia_investigation_attempts SET evidence_manifest = %s::jsonb WHERE id = %s::uuid;",
            (json.dumps(manifest, default=str), attempt_id),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("evidence manifest not recorded attempt=%s: %s", attempt_id, type(exc).__name__)
    return out


def _run_ollama(
    *, alert_id: str, tenant_id: str, alert: Dict[str, Any], limited: bool
) -> Optional[Dict[str, Any]]:
    timeout = _llm_timeout_seconds()
    try:
        triage = run_tier1_triage(
            alert_id=alert_id,
            tenant_id=tenant_id,
            alert=alert,
            customer_safe=False,
            force=False,
            llm_timeout_seconds=timeout,
            limited_evidence=limited,
        )
        # A rule-based result cached by an 8s dashboard timeout must not stand in
        # for a real model verdict here.
        if triage.get("cached") and triage.get("execution_status") == "degraded" and not limited:
            triage = run_tier1_triage(
                alert_id=alert_id,
                tenant_id=tenant_id,
                alert=alert,
                customer_safe=False,
                force=True,
                llm_timeout_seconds=timeout,
                limited_evidence=limited,
            )
        return triage
    except Exception as exc:  # noqa: BLE001
        logger.warning("Deep triage (Ollama) failed id=%s: %s", alert_id, type(exc).__name__)
        return None
