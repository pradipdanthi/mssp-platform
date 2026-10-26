"""KB-117: Expert SOC agent stage — map Cursor agent output onto existing AI fields.

Never auto-executes EDR isolate or ITDR remediate. Persists draft suggestions
and optional customer recommendations; escalation reuses ai_deep_triage rules.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.db.session import fetch_one, fetch_one_write
from app.services.soc_agent_client import (
    forward_alert_for_expert_triage,
    soc_agent_enabled,
)

logger = logging.getLogger(__name__)

_VERDICT_MAP = {
    "critical": "MALICIOUS",
    "malicious": "MALICIOUS",
    "suspicious": "SUSPICIOUS",
    "benign": "BENIGN_FALSE_POSITIVE",
    "benign_false_positive": "BENIGN_FALSE_POSITIVE",
    "false_positive": "BENIGN_FALSE_POSITIVE",
}


def map_agent_verdict(raw: Optional[str]) -> str:
    key = (raw or "").strip().lower().replace(" ", "_")
    return _VERDICT_MAP.get(key, "SUSPICIOUS")


def extract_action_package(agent_result: Dict[str, Any]) -> Dict[str, Any]:
    llm = agent_result.get("llm") if isinstance(agent_result.get("llm"), dict) else {}
    pkg = llm.get("action_package") or agent_result.get("action_package") or {}
    if not isinstance(pkg, dict):
        pkg = {}
    # Defaults from escalate / recommended_actions when package missing
    escalate = bool(llm.get("escalate_to_human") or agent_result.get("escalate_to_human"))
    actions = llm.get("recommended_actions") or []
    action_blob = " ".join(str(a) for a in actions).lower()
    return {
        "propose_edr_isolate": bool(
            pkg.get("propose_edr_isolate")
            or "isolate" in action_blob
            or "contain" in action_blob
        ),
        "propose_itdr_remediate": bool(
            pkg.get("propose_itdr_remediate")
            or "disable user" in action_blob
            or "revoke" in action_blob
            or "itdr" in action_blob
        ),
        "propose_case_note": bool(pkg.get("propose_case_note", True)),
        "propose_customer_recommendation": bool(
            pkg.get("propose_customer_recommendation")
            or llm.get("customer_action")
        ),
        "escalate_human": bool(pkg.get("escalate_human", escalate)),
        "customer_action_title": str(
            pkg.get("customer_action_title") or llm.get("customer_action_title") or ""
        )[:500],
        "customer_action_body": str(
            pkg.get("customer_action_body")
            or llm.get("customer_action_body")
            or llm.get("customer_safe_summary")
            or ""
        )[:4000],
        "notes": str(pkg.get("notes") or "")[:2000],
    }


def agent_result_to_triage(agent_result: Dict[str, Any]) -> Dict[str, Any]:
    """Shape compatible with ai_deep_triage.decide_escalation / Tier-1 fields."""
    llm = agent_result.get("llm") if isinstance(agent_result.get("llm"), dict) else {}
    verdict_raw = llm.get("verdict") or agent_result.get("verdict") or "Suspicious"
    verdict = map_agent_verdict(str(verdict_raw))
    try:
        confidence = float(llm.get("confidence") if llm.get("confidence") is not None else 50)
    except (TypeError, ValueError):
        confidence = 50.0
    confidence = max(0.0, min(100.0, confidence))

    pkg = extract_action_package(agent_result)
    recommended_action = "INVESTIGATE_HOST"
    if pkg["propose_edr_isolate"]:
        recommended_action = "ISOLATE_AGENT"
    elif pkg["propose_itdr_remediate"]:
        recommended_action = "DISABLE_USER"
    elif pkg["escalate_human"]:
        recommended_action = "ESCALATE_HUMAN"

    summary = str(llm.get("summary") or "")[:4000]
    actions = llm.get("recommended_actions") or []
    containment = "; ".join(str(a) for a in actions[:6])[:4000]
    if pkg["propose_edr_isolate"]:
        containment = (
            "PROPOSED (human approval required): isolate host via EDR. " + containment
        )[:4000]
    if pkg["propose_itdr_remediate"]:
        containment = (
            "PROPOSED (human approval required): ITDR identity remediate. " + containment
        )[:4000]

    mitre = llm.get("mitre") or []
    mitre_note = ""
    if isinstance(mitre, list) and mitre:
        bits = []
        for m in mitre[:8]:
            if isinstance(m, dict):
                bits.append(f"{m.get('technique_id')}:{m.get('technique_name')}")
        mitre_note = "MITRE: " + ", ".join(bits)

    return {
        "verdict": verdict,
        "confidence": confidence,
        "recommended_action": recommended_action,
        "model": "cursor-soc-agent",
        "summary": summary,
        "root_cause": str(llm.get("root_cause") or "")[:2000],
        "containment_suggestion": containment or None,
        "enrichment_notes": mitre_note or None,
        "risk_score": confidence,
        "risk_rationale": summary[:2000] if summary else None,
        "action_package": pkg,
        "false_positive_likelihood": llm.get("false_positive_likelihood"),
        "dossier_id": agent_result.get("dossier_id"),
        "provider": (agent_result.get("llm_meta") or {}).get("provider"),
    }


def persist_expert_fields(
    *,
    alert_id: str,
    tenant_id: str,
    triage: Dict[str, Any],
) -> None:
    """Write expert results into the same AI columns Admin already shows."""
    pkg = triage.get("action_package") or {}
    pkg_json = json.dumps(pkg, default=str)[:3500]
    enrichment = triage.get("enrichment_notes") or ""
    if pkg_json and pkg_json != "{}":
        enrichment = (enrichment + "\naction_package=" + pkg_json).strip()[:4000]

    # Schema only allows ai_queue NULL or 'low_priority' (see 039_ai_tier1_queue_persist.sql)
    verdict = str(triage.get("verdict") or "")
    confidence = float(triage.get("confidence") or 0)
    ai_queue = (
        "low_priority"
        if verdict == "BENIGN_FALSE_POSITIVE" and confidence >= 85.0
        else None
    )

    fetch_one_write(
        """
        UPDATE security_alerts
        SET
          ai_verdict = %s,
          ai_confidence = %s,
          ai_queue = %s,
          ai_plain_summary = COALESCE(NULLIF(btrim(%s), ''), ai_plain_summary),
          ai_technical_summary = COALESCE(NULLIF(btrim(%s), ''), ai_technical_summary),
          ai_recommended_action = COALESCE(NULLIF(btrim(%s), ''), ai_recommended_action),
          ai_risk_score = %s,
          ai_risk_rationale = COALESCE(NULLIF(btrim(%s), ''), ai_risk_rationale),
          ai_enrichment_notes = COALESCE(NULLIF(btrim(%s), ''), ai_enrichment_notes),
          ai_containment_suggestion = COALESCE(NULLIF(btrim(%s), ''), ai_containment_suggestion),
          ai_triage_status = 'draft',
          ai_triaged_at = now(),
          updated_at = now()
        WHERE id = %s::uuid
          AND tenant_id = %s::uuid
          AND COALESCE(ai_triage_status, '') <> 'accepted'
        RETURNING id::text;
        """,
        (
            verdict,
            confidence,
            ai_queue,
            triage.get("summary") or "",
            triage.get("root_cause") or "",
            triage.get("recommended_action") or "",
            float(triage.get("risk_score") or confidence),
            triage.get("risk_rationale") or "",
            enrichment,
            triage.get("containment_suggestion") or "",
            alert_id,
            tenant_id,
        ),
    )


def maybe_create_customer_recommendation(
    *,
    alert_id: str,
    tenant_id: str,
    triage: Dict[str, Any],
) -> Optional[str]:
    """Idempotent: at most one open SOC-agent recommendation per alert."""
    pkg = triage.get("action_package") or {}
    if not pkg.get("propose_customer_recommendation"):
        return None
    title = (pkg.get("customer_action_title") or "").strip()
    body = (pkg.get("customer_action_body") or triage.get("summary") or "").strip()
    if not title:
        title = "Security action recommended by SOC analysis"
    if not body:
        return None

    existing = fetch_one(
        """
        SELECT id::text AS id
        FROM customer_recommendations
        WHERE related_alert_id = %s::uuid
          AND category = 'soc_agent'
          AND status IN ('open', 'in_progress')
        LIMIT 1;
        """,
        (alert_id,),
    )
    if existing:
        return existing["id"]

    priority = "high"
    verdict = str(triage.get("verdict") or "")
    if verdict == "MALICIOUS":
        priority = "critical"
    elif verdict == "BENIGN_FALSE_POSITIVE":
        priority = "low"

    row = fetch_one_write(
        """
        INSERT INTO customer_recommendations (
            tenant_id, related_alert_id, title, description,
            priority, category, status, customer_visible
        )
        VALUES (
            %s::uuid, %s::uuid, %s, %s,
            %s, 'soc_agent', 'open', false
        )
        RETURNING id::text AS id;
        """,
        (tenant_id, alert_id, title[:500], body[:20000], priority),
    )
    return (row or {}).get("id")


def run_expert_on_alert(
    *,
    alert_id: str,
    tenant_id: str,
    alert: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Call agent, persist fields, optional recommendation. Returns triage dict or None."""
    if not soc_agent_enabled():
        return None
    result = forward_alert_for_expert_triage(alert)
    if not result or not result.get("ok"):
        return None
    triage = agent_result_to_triage(result)
    try:
        persist_expert_fields(alert_id=alert_id, tenant_id=tenant_id, triage=triage)
        rec_id = maybe_create_customer_recommendation(
            alert_id=alert_id, tenant_id=tenant_id, triage=triage
        )
        if rec_id:
            triage["recommendation_id"] = rec_id
    except Exception:  # noqa: BLE001
        logger.exception("Failed persisting SOC agent expert fields id=%s", alert_id)
        return None
    logger.info(
        "SOC agent expert complete id=%s verdict=%s confidence=%.1f provider=%s",
        alert_id,
        triage.get("verdict"),
        triage.get("confidence") or 0,
        triage.get("provider"),
    )
    return triage


def apply_callback_payload(
    *,
    alert_id: str,
    tenant_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply a push callback from the agent (same persist path as pull)."""
    # Allow either full ingest-shaped result or a slim triage body.
    if payload.get("llm") or payload.get("verdict"):
        triage = agent_result_to_triage(payload if payload.get("ok") is not False else {**payload, "ok": True})
    else:
        triage = {
            "verdict": map_agent_verdict(str(payload.get("verdict") or "Suspicious")),
            "confidence": float(payload.get("confidence") or 50),
            "recommended_action": payload.get("recommended_action") or "INVESTIGATE_HOST",
            "model": "cursor-soc-agent-callback",
            "summary": str(payload.get("summary") or "")[:4000],
            "root_cause": str(payload.get("root_cause") or "")[:2000],
            "containment_suggestion": str(payload.get("containment_suggestion") or "")[:4000],
            "enrichment_notes": str(payload.get("enrichment_notes") or "")[:4000],
            "risk_score": float(payload.get("confidence") or 50),
            "risk_rationale": str(payload.get("summary") or "")[:2000],
            "action_package": extract_action_package(payload),
        }
    persist_expert_fields(alert_id=alert_id, tenant_id=tenant_id, triage=triage)
    rec_id = maybe_create_customer_recommendation(
        alert_id=alert_id, tenant_id=tenant_id, triage=triage
    )
    return {"ok": True, "alert_id": alert_id, "triage": triage, "recommendation_id": rec_id}
