"""
KB-096 Phase 1: AI SOC Triage Assist — enrich + correlate + risk draft.

Complements Threat Intelligence (IOC system of record). Reads TI matches and
related open cases, then asks the local LLM for analyst-facing draft notes.
Human SOC always finalizes. Never flips customer portal visibility or runs containment.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from app.db.session import fetch_all, fetch_one, fetch_one_write

logger = logging.getLogger(__name__)

_SECRET_RE = re.compile(
    r"(?i)(password|passwd|api[_-]?key|token|secret|authorization|bearer)\s*[:=]\s*\S+"
)


def ai_soc_triage_enabled() -> bool:
    return (os.getenv("AI_SOC_TRIAGE_ENABLED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _min_severity_rank() -> int:
    raw = (os.getenv("AI_ALERT_MIN_SEVERITY") or "high").strip().lower()
    ranks = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    return ranks.get(raw, 3)


def _severity_ok(severity: Optional[str]) -> bool:
    ranks = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    return ranks.get((severity or "").strip().lower(), 0) >= _min_severity_rank()


def _redact(text: str, limit: int = 2000) -> str:
    cleaned = _SECRET_RE.sub(r"\1=[REDACTED]", text or "")
    cleaned = re.sub(r"\b[A-Za-z0-9_\-]{32,}\b", "[REDACTED_TOKEN]", cleaned)
    if len(cleaned) > limit:
        return cleaned[:limit] + "…"
    return cleaned


def _call_llm(prompt: str) -> Dict[str, Any]:
    base = (os.getenv("AI_ALERT_BASE_URL") or "").rstrip("/")
    model = (os.getenv("AI_ALERT_MODEL") or "qwen2.5:14b").strip()
    api_key = (os.getenv("AI_ALERT_API_KEY") or "ollama").strip()
    timeout = int(os.getenv("AI_ALERT_TIMEOUT_SECONDS") or "90")
    if not base:
        raise RuntimeError("AI_ALERT_BASE_URL not configured")

    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an MSSP SOC triage assistant. Return ONLY valid JSON with keys: "
                    "enrichment_notes (string), correlation_notes (string), "
                    "risk_score (number 0-100), risk_rationale (string), "
                    "containment_suggestion (string). "
                    "Cite Threat Intel IOC matches when present. Do not invent IOCs. "
                    "containment_suggestion must be a draft for a HUMAN analyst to decide "
                    "(e.g. isolate host, disable user, block IOC) — never imply the system "
                    "will auto-contain. If no containment is warranted, say so clearly. "
                    "Be concise and actionable for a human analyst."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    content = (
        ((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    ).strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    parsed = json.loads(content)
    score = parsed.get("risk_score")
    try:
        score_f = float(score)
    except (TypeError, ValueError):
        score_f = 50.0
    score_f = max(0.0, min(100.0, score_f))
    return {
        "enrichment_notes": str(parsed.get("enrichment_notes") or "")[:4000],
        "correlation_notes": str(parsed.get("correlation_notes") or "")[:4000],
        "risk_score": score_f,
        "risk_rationale": str(parsed.get("risk_rationale") or "")[:4000],
        "containment_suggestion": str(parsed.get("containment_suggestion") or "")[:4000],
    }


def _load_ti_context(tenant_id: str, alert: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pull recent TI IOCs for tenant — AI cites these; TI remains source of truth."""
    blob = " ".join(
        [
            str(alert.get("alert_title") or ""),
            str(alert.get("alert_description") or ""),
            str(alert.get("ai_plain_summary") or ""),
            str(alert.get("destination_host") or ""),
        ]
    )
    rows = fetch_all(
        """
        SELECT ioc_type, ioc_value, reputation_status, confidence_score,
               mitre_tactics, summary
        FROM tenant_threat_intel_iocs
        WHERE tenant_id = %s::uuid AND status = 'active'
        ORDER BY
          CASE reputation_status
            WHEN 'MALICIOUS' THEN 0
            WHEN 'SUSPICIOUS' THEN 1
            ELSE 2
          END,
          confidence_score DESC NULLS LAST
        LIMIT 40;
        """,
        (tenant_id,),
    )
    matched: List[Dict[str, Any]] = []
    for row in rows or []:
        val = str(row.get("ioc_value") or "").strip()
        if val and val.lower() in blob.lower():
            matched.append(dict(row))
    # Always include top malicious/suspicious for analyst context even if not in blob
    if not matched:
        for row in (rows or [])[:8]:
            matched.append(dict(row))
    return matched[:12]


def _load_correlation_context(tenant_id: str, alert: Dict[str, Any]) -> Dict[str, Any]:
    host = (alert.get("destination_host") or "").strip()
    title = (alert.get("alert_title") or "").strip()
    related_alerts = fetch_all(
        """
        SELECT id::text, alert_title, severity, status, event_time::text, destination_host
        FROM security_alerts
        WHERE tenant_id = %s::uuid
          AND id <> %s::uuid
          AND (
            (%s <> '' AND destination_host = %s)
            OR (%s <> '' AND alert_title = %s)
          )
        ORDER BY event_time DESC NULLS LAST
        LIMIT 8;
        """,
        (tenant_id, alert["id"], host, host, title, title),
    )
    open_incidents = fetch_all(
        """
        SELECT incident_number, title, severity, status, opened_at::text
        FROM incidents
        WHERE tenant_id = %s::uuid
          AND status IN ('open', 'in_progress', 'waiting_customer')
        ORDER BY opened_at DESC
        LIMIT 8;
        """,
        (tenant_id,),
    )
    return {
        "related_alerts": related_alerts or [],
        "open_incidents": open_incidents or [],
    }


def build_triage_prompt(
    alert: Dict[str, Any],
    ti_hits: List[Dict[str, Any]],
    corr: Dict[str, Any],
) -> str:
    return "\n".join(
        [
            "Draft SOC triage assist for this alert. Human analyst will finalize.",
            "Containment is a HUMAN decision — provide a suggestion only, never an action.",
            f"Title: {_redact(str(alert.get('alert_title') or ''))}",
            f"Severity: {alert.get('severity')}",
            f"Host: {_redact(str(alert.get('destination_host') or ''))}",
            f"Source: {alert.get('source_tool')}",
            f"Description: {_redact(str(alert.get('alert_description') or ''), 800)}",
            f"Existing plain summary: {_redact(str(alert.get('ai_plain_summary') or ''), 600)}",
            "Threat Intel IOC context (system of record — cite, do not invent):",
            _redact(json.dumps(ti_hits, default=str)[:1800]),
            "Related alerts:",
            _redact(json.dumps(corr.get("related_alerts") or [], default=str)[:1200]),
            "Open incidents for tenant:",
            _redact(json.dumps(corr.get("open_incidents") or [], default=str)[:1200]),
        ]
    )


def process_soc_triage_job(*, alert_id: str, tenant_id: str) -> bool:
    """
    Produce AI draft enrich/correlate/risk fields.
    Skips if disabled, severity too low, or already accepted by human.
    """
    if not ai_soc_triage_enabled():
        return False

    alert = fetch_one(
        """
        SELECT id::text AS id, tenant_id::text AS tenant_id, severity, alert_title,
               alert_description, destination_host, source_tool, ai_plain_summary,
               ai_risk_score, ai_triage_status
        FROM security_alerts
        WHERE id = %s::uuid AND tenant_id = %s::uuid
        LIMIT 1;
        """,
        (alert_id, tenant_id),
    )
    if not alert:
        return False
    if not _severity_ok(alert.get("severity")):
        return False
    if (alert.get("ai_triage_status") or "").strip() == "accepted":
        return True

    ti_hits = _load_ti_context(tenant_id, alert)
    corr = _load_correlation_context(tenant_id, alert)

    try:
        result = _call_llm(build_triage_prompt(alert, ti_hits, corr))
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI SOC triage failed id=%s: %s", alert_id, exc)
        return False

    # Prefer structured TI citation when matches exist
    if ti_hits and not result["enrichment_notes"]:
        cites = ", ".join(
            f"{h.get('ioc_type')}:{h.get('ioc_value')} ({h.get('reputation_status')})"
            for h in ti_hits[:5]
        )
        result["enrichment_notes"] = f"Threat Intel matches considered: {cites}"

    fetch_one_write(
        """
        UPDATE security_alerts
        SET
          ai_risk_score = %s,
          ai_risk_rationale = %s,
          ai_enrichment_notes = %s,
          ai_correlation_notes = %s,
          ai_containment_suggestion = %s,
          ai_triage_status = 'draft',
          ai_triaged_at = now(),
          updated_at = now()
        WHERE id = %s::uuid AND tenant_id = %s::uuid
          AND COALESCE(ai_triage_status, '') <> 'accepted'
        RETURNING id::text;
        """,
        (
            result["risk_score"],
            result["risk_rationale"] or None,
            result["enrichment_notes"] or None,
            result["correlation_notes"] or None,
            result["containment_suggestion"] or None,
            alert_id,
            tenant_id,
        ),
    )
    logger.info(
        "AI SOC triage draft written id=%s risk=%s ti_hits=%s",
        alert_id,
        result["risk_score"],
        len(ti_hits),
    )
    return True
