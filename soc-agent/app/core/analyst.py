"""Full SOC analyst pipeline: parse → OSINT → heuristic → LLM → verdict."""

from __future__ import annotations

import json
from typing import Any

from app.audit import audit
from app.config import settings
from app.core.callback import push_triage_result
from app.core.llm_provider import LLMRouter
from app.core.osint import enrich_osint
from app.enrichment import enrich_alert
from app.triage import triage, write_dossier


def run_analyst(alert: dict[str, Any]) -> dict[str, Any]:
    cfg = settings()
    audit_path = cfg.get("triage_audit_log") or "/var/log/soc-agent/triage_audit.log"

    audit(audit_path, "analyst.start", {"alert_id": alert.get("alert_id"), "title": alert.get("title")})

    local = enrich_alert(alert)
    osint = enrich_osint(alert)
    heuristic = triage(alert, local)

    audit(
        audit_path,
        "analyst.enrichment",
        {
            "alert_id": alert.get("alert_id"),
            "local_src": local.get("source_reputation"),
            "mitre_heuristic": local.get("mitre"),
            "osint": osint,
            "heuristic": heuristic,
        },
    )

    prompt = json.dumps(
        {
            "alert": alert,
            "local_enrichment": local,
            "osint": osint,
            "heuristic_triage": heuristic,
        },
        default=str,
    )

    llm_verdict: dict[str, Any] | None = None
    llm_meta: dict[str, Any] = {}
    try:
        llm_verdict, llm_meta = LLMRouter().triage(prompt)
        audit(
            audit_path,
            "analyst.llm",
            {"alert_id": alert.get("alert_id"), "meta": llm_meta, "verdict": llm_verdict},
        )
    except Exception as exc:  # noqa: BLE001
        audit(
            audit_path,
            "analyst.llm_failed",
            {"alert_id": alert.get("alert_id"), "error": str(exc)[:500]},
        )
        # Soft fallback only if Cursor call fails mid-flight; ingest already
        # refuses when CURSOR_API_KEY is missing.
        llm_verdict = {
            "verdict": (
                "Critical"
                if heuristic["disposition"] == "escalate"
                else "Suspicious"
                if heuristic["score"] >= 25
                else "Benign"
            ),
            "confidence": heuristic["score"],
            "summary": "Cursor LLM call failed — heuristic only. " + "; ".join(heuristic["reasons"]),
            "root_cause": "cursor_llm_error",
            "mitre": local.get("mitre") or [],
            "recommended_actions": [
                "Check CURSOR_API_KEY and agent CLI on VM 117",
                "Re-run ingest after Cursor auth is healthy",
            ],
            "false_positive_likelihood": "medium",
            "escalate_to_human": True,
        }
        llm_meta = {"provider": "heuristic_fallback_cursor_error", "error": str(exc)[:200]}

    verdict = str(llm_verdict.get("verdict") or "Suspicious")
    escalate = bool(llm_verdict.get("escalate_to_human")) or verdict == "Critical"
    dossier_id = None
    if escalate or verdict in ("Critical", "Suspicious"):
        dossier_id = write_dossier(
            cfg["dossier_dir"],
            alert,
            {"local": local, "osint": osint, "llm": llm_verdict},
            {
                "score": int(llm_verdict.get("confidence") or heuristic["score"]),
                "disposition": "escalate" if escalate else "investigate",
                "classification": verdict.lower(),
                "reasons": ["llm_analyst"],
                "severity_in": alert.get("severity"),
                "mitre_ids": [m.get("technique_id") for m in (llm_verdict.get("mitre") or []) if isinstance(m, dict)],
            },
        )
        audit(audit_path, "analyst.dossier", {"dossier_id": dossier_id})

    result = {
        "ok": True,
        "alert_id": alert.get("alert_id"),
        "verdict": verdict,
        "llm": llm_verdict,
        "llm_meta": llm_meta,
        "heuristic": heuristic,
        "enrichment": {"local": local, "osint": osint},
        "dossier_id": dossier_id,
        "human_soc_effort": (
            "escalated_for_human_review"
            if escalate
            else "auto_closed_or_low_touch"
        ),
    }
    # Push to control plane when configured (fail-soft; local result still returned)
    try:
        cb = push_triage_result(result, alert)
        if cb is not None:
            result["mssp_callback"] = {"ok": True, "response": cb}
            audit(audit_path, "analyst.callback_ok", {"alert_id": alert.get("alert_id")})
        else:
            result["mssp_callback"] = {"ok": False, "skipped": True}
    except Exception as exc:  # noqa: BLE001
        result["mssp_callback"] = {"ok": False, "error": str(exc)[:200]}
        audit(
            audit_path,
            "analyst.callback_failed",
            {"alert_id": alert.get("alert_id"), "error": str(exc)[:300]},
        )

    audit(audit_path, "analyst.complete", {"alert_id": alert.get("alert_id"), "verdict": verdict, "dossier_id": dossier_id})
    return result
