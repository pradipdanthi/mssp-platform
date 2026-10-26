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
  - Idempotent per alert. One escalation per alert unless it is re-opened.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from app.db.session import fetch_one, fetch_one_write
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
    """Decide whether this alert wakes a human, using fixed rules only.

    Returns {"escalate": bool, "urgency": str, "reasons": [str], ...}.
    """
    verdict = str(triage.get("verdict") or "").strip().upper()
    action = str(triage.get("recommended_action") or "").strip().upper()
    try:
        confidence = float(triage.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    severity = (alert.get("severity") or "").strip().lower()
    severity_rank = _SEVERITY_RANKS.get(severity, 0)
    asset_tier = (alert.get("asset_criticality") or "").strip().lower()
    model = str(triage.get("model") or "")
    degraded = "fallback" in model

    reasons: List[str] = []
    escalate = False
    urgency = "normal"

    if verdict == "MALICIOUS" and confidence >= _escalate_confidence_floor():
        escalate = True
        urgency = "high"
        reasons.append(f"AI verdict MALICIOUS at {confidence:.0f}% confidence")

    if action == "ISOLATE_AGENT":
        escalate = True
        urgency = "high"
        reasons.append("AI recommends host isolation — needs human approval")

    if verdict == "SUSPICIOUS" and severity_rank >= _SEVERITY_RANKS["critical"]:
        escalate = True
        reasons.append("Suspicious verdict on a critical-severity alert")

    if escalate and asset_tier in _CRITICAL_ASSET_TIERS:
        urgency = "high"
        reasons.append(f"Asset criticality is {asset_tier}")

    # Fail toward the human: if the model could not judge and the alert is
    # severe, a person decides rather than nobody.
    if degraded and severity_rank >= _SEVERITY_RANKS["critical"]:
        escalate = True
        urgency = "high"
        reasons.append("AI degraded (model unavailable) on a critical alert")

    if verdict == "BENIGN_FALSE_POSITIVE" and not degraded and action != "ISOLATE_AGENT":
        silence_floor = _benign_silence_confidence()
        if severity_rank >= _SEVERITY_RANKS["critical"] and confidence < silence_floor:
            escalate = True
            urgency = "normal"
            reasons = [
                f"AI leans benign at {confidence:.0f}% on a critical alert — "
                f"below the {silence_floor:.0f}% bar to stay silent; human confirms"
            ]
        else:
            escalate = False
            urgency = "normal"
            reasons = ["AI assessed benign false positive — no human wake"]

    return {
        "escalate": escalate,
        "urgency": urgency,
        "reasons": reasons,
        "verdict": verdict or None,
        "confidence": confidence,
        "recommended_action": action or None,
        "degraded": degraded,
    }


def build_escalation_message(alert: Dict[str, Any], decision: Dict[str, Any]) -> str:
    """Human-readable page body. Carries the analysis, not just a wake-up ping."""
    host = alert.get("asset_hostname") or alert.get("destination_host") or "unknown host"
    tenant = alert.get("tenant_name") or alert.get("short_code") or "unknown tenant"
    severity = (alert.get("severity") or "unknown").upper()
    verdict = decision.get("verdict") or "UNKNOWN"
    confidence = decision.get("confidence") or 0.0
    summary = (alert.get("ai_plain_summary") or alert.get("alert_title") or "").strip()
    action = decision.get("recommended_action") or "INVESTIGATE_HOST"
    reasons = "; ".join(decision.get("reasons") or []) or "escalation rules matched"

    lines = [
        f"[{severity}] Kevantic SOC escalation — {tenant}",
        f"Host: {host}",
        f"AI verdict: {verdict} ({confidence:.0f}% confidence)",
        f"Suggested next step: {action}",
        "",
        summary[:600],
        "",
        f"Why you were paged: {reasons}",
        f"Alert ID: {alert.get('id')}",
    ]
    return "\n".join(line for line in lines if line is not None)


def _already_escalated(alert_id: str) -> bool:
    row = fetch_one(
        """
        SELECT 1 AS hit
        FROM notification_events
        WHERE alert_id = %s::uuid
          AND status <> 'failed'
        LIMIT 1;
        """,
        (alert_id,),
    )
    return bool(row)


def record_escalation(
    *,
    alert: Dict[str, Any],
    decision: Dict[str, Any],
    channel: str,
    recipient_address: str,
    recipient_name: Optional[str] = None,
) -> Optional[str]:
    """Queue one escalation for the notification worker to deliver."""
    body = build_escalation_message(alert, decision)
    row = fetch_one_write(
        """
        INSERT INTO notification_events (
            tenant_id, alert_id, notification_type, recipient_name,
            recipient_address, message_body, status
        )
        VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, 'queued')
        RETURNING id::text AS id;
        """,
        (
            alert.get("tenant_id"),
            alert.get("id"),
            channel,
            recipient_name,
            recipient_address,
            body,
        ),
    )
    return (row or {}).get("id")


def _oncall_recipients() -> List[Dict[str, str]]:
    """On-call roster from env until a managed roster table exists.

    SOC_ONCALL_WHATSAPP="+919000000001,+919000000002"
    SOC_ONCALL_NAME="Kevantic SOC on-call"
    """
    raw = (os.getenv("SOC_ONCALL_WHATSAPP") or "").strip()
    name = (os.getenv("SOC_ONCALL_NAME") or "Kevantic SOC on-call").strip()
    out: List[Dict[str, str]] = []
    for entry in raw.split(","):
        number = entry.strip()
        if number:
            out.append({"address": number, "name": name})
    return out


def process_deep_triage_job(*, alert_id: str, tenant_id: str) -> bool:
    """Run expert (Cursor SOC agent) or Ollama Tier-1 deep triage, then escalate.

    When SOC_AGENT_ENABLED, prefer the Cursor agent on VM 117 (no parallel
    Ollama deep call). Fall back to existing run_tier1_triage if the agent
    is down or returns nothing. Never auto-contains.
    """
    from app.services.soc_agent_client import soc_agent_enabled
    from app.services.soc_agent_expert import run_expert_on_alert

    agent_on = soc_agent_enabled()
    if not deep_triage_enabled() and not agent_on:
        return False

    alert = load_alert_for_triage(alert_id, tenant_id)
    if not alert:
        logger.info("Deep triage skipped — alert not found id=%s", alert_id)
        return False

    # Severity gate: agent uses SOC_AGENT_MIN_SEVERITY; Ollama deep uses
    # AI_DEEP_TRIAGE_MIN_SEVERITY. Allow the job if either path would accept.
    from app.services.soc_agent_client import severity_meets_agent_threshold

    severity_ok = False
    if agent_on and severity_meets_agent_threshold(alert.get("severity")):
        severity_ok = True
    if deep_triage_enabled() and _severity_ok(alert.get("severity")):
        severity_ok = True
    if not severity_ok:
        return False

    if (alert.get("ai_triage_status") or "").strip() == "accepted":
        return True

    triage: Optional[Dict[str, Any]] = None

    if agent_on and severity_meets_agent_threshold(alert.get("severity")):
        try:
            triage = run_expert_on_alert(
                alert_id=alert_id, tenant_id=tenant_id, alert=alert
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("SOC agent expert failed id=%s: %s", alert_id, exc)
            triage = None

    if triage is None and deep_triage_enabled():
        timeout = _llm_timeout_seconds()
        try:
            triage = run_tier1_triage(
                alert_id=alert_id,
                tenant_id=tenant_id,
                alert=alert,
                customer_safe=False,
                force=False,
                llm_timeout_seconds=timeout,
            )
            # A rule-based result cached by an 8s dashboard timeout must not stand in
            # for a real model verdict here.
            if triage.get("cached") and triage.get("model") == "rule_based_fallback":
                triage = run_tier1_triage(
                    alert_id=alert_id,
                    tenant_id=tenant_id,
                    alert=alert,
                    customer_safe=False,
                    force=True,
                    llm_timeout_seconds=timeout,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Deep triage failed id=%s: %s", alert_id, exc)
            return False

    if triage is None:
        logger.warning("Deep triage produced no result id=%s", alert_id)
        return False

    decision = decide_escalation(alert, triage)
    logger.info(
        "Deep triage complete id=%s verdict=%s confidence=%.2f escalate=%s urgency=%s",
        alert_id,
        decision.get("verdict"),
        decision.get("confidence") or 0.0,
        decision.get("escalate"),
        decision.get("urgency"),
    )

    if not decision.get("escalate"):
        return True

    if _already_escalated(alert_id):
        logger.info("Deep triage escalation suppressed — already paged id=%s", alert_id)
        return True

    recipients = _oncall_recipients()
    if not recipients:
        logger.warning(
            "Deep triage wants to escalate id=%s but SOC_ONCALL_WHATSAPP is empty",
            alert_id,
        )
        return True

    channel = (os.getenv("SOC_ESCALATION_CHANNEL") or "whatsapp").strip().lower()
    for person in recipients:
        try:
            event_id = record_escalation(
                alert=alert,
                decision=decision,
                channel=channel,
                recipient_address=person["address"],
                recipient_name=person.get("name"),
            )
            logger.info(
                "SOC escalation queued alert=%s event=%s channel=%s urgency=%s",
                alert_id,
                event_id,
                channel,
                decision.get("urgency"),
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to queue SOC escalation alert=%s", alert_id)

    return True
