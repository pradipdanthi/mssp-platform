"""KB-117: Expert SOC agent stage — map Cursor agent output onto existing AI fields.

Never auto-executes EDR isolate or ITDR remediate. Persists draft suggestions
and optional customer recommendations; escalation reuses ai_deep_triage rules.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.db.session import fetch_one, fetch_one_write
from app.services import tia_investigation as tia

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


def _run_write(cur, query: str, params: tuple) -> Dict[str, Any]:
    """Execute inside the caller's transaction when a cursor is given."""
    if cur is None:
        return fetch_one_write(query, params)
    cur.execute(query, params)
    row = cur.fetchone()
    return dict(row) if row else {}


def _run_read(cur, query: str, params: tuple) -> Dict[str, Any]:
    if cur is None:
        return fetch_one(query, params)
    cur.execute(query, params)
    row = cur.fetchone()
    return dict(row) if row else {}


def persist_expert_fields(
    *,
    alert_id: str,
    tenant_id: str,
    triage: Dict[str, Any],
    cur=None,
) -> None:
    """Write expert results into the same AI columns Admin already shows."""
    if triage.get("execution_status") != "succeeded":
        # Only a validated, completed analysis may write verdict fields.
        raise ValueError("refusing to persist verdict fields from a non-succeeded investigation")
    pkg = triage.get("action_package") or {}
    pkg_json = json.dumps(pkg, default=str)[:3500]
    enrichment = triage.get("enrichment_notes") or ""
    if pkg_json and pkg_json != "{}":
        enrichment = (enrichment + "\naction_package=" + pkg_json).strip()[:4000]

    # Schema only allows ai_queue NULL or 'low_priority' (see 039_ai_tier1_queue_persist.sql)
    verdict = str(triage.get("verdict") or "")
    confidence = float(triage.get("confidence") or 0)
    # Never bury an alert the model itself flagged for review or that arrived as
    # critical severity; a benign recommendation there stays in the actionable queue.
    ai_queue = (
        "low_priority"
        if verdict == "BENIGN_FALSE_POSITIVE"
        and confidence >= 85.0
        and not triage.get("model_review_requested")
        and str(triage.get("source_severity") or "").lower() != "critical"
        else None
    )

    _run_write(
        cur,
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
    cur=None,
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

    existing = _run_read(
        cur,
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

    row = _run_write(
        cur,
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


def outcome_to_triage(outcome: "tia.Outcome") -> Dict[str, Any]:
    """Triage dict for the escalation rules and persistence.

    A succeeded outcome carries a validated analysis. Any other outcome carries no
    verdict at all: verdict/confidence/action are None so nothing downstream can
    read a conclusion that does not exist.
    """
    if outcome.succeeded and outcome.llm is not None:
        triage = agent_result_to_triage(
            {
                "llm": outcome.llm,
                "dossier_id": outcome.dossier_id,
                "llm_meta": {"provider": outcome.provenance.get("provider")},
            }
        )
        triage["model"] = outcome.provenance.get("provider") or "cursor-agent"
        triage["execution_status"] = "succeeded"
        triage["disposition"] = outcome.disposition
        triage["model_review_requested"] = outcome.model_review_requested
        triage["source_severity"] = outcome.source_severity
        triage["provenance"] = outcome.provenance
        return triage
    return {
        "verdict": None,
        "confidence": None,
        "recommended_action": None,
        "model": outcome.provenance.get("provider") or "cursor-agent",
        "execution_status": outcome.execution_status,
        "error_category": outcome.error_category,
        "disposition": "unset",
        "model_review_requested": True,
        "source_severity": outcome.source_severity,
        "provenance": outcome.provenance,
        "limited_evidence": outcome.limited_evidence,
        "outcome": outcome,
    }
