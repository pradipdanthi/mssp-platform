"""Full SOC analyst pipeline: parse → OSINT → heuristic → LLM → validated result.

Result contract (analyst-result-2):
  execution.status   succeeded | failed | timed_out   (what happened to the call)
  disposition        malicious | inconclusive | unset
                     (what the validated analysis recommends; unset when no
                     analysis completed; never false_positive or authorized_benign)
  source_severity    severity as received, never modified here
  human_review       the agent may REQUEST review; the control plane decides

A failed call never produces a verdict. The local heuristic is attached as
limited_evidence and is not a conclusion.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.audit import audit
from app.config import settings
from app.core.callback import push_triage_result
from app.core.llm_provider import (
    PROMPT_VERSION,
    CursorAgentProvider,
    LLMRouter,
    ProviderError,
    redact,
)
from app.core.osint import enrich_osint
from app.enrichment import enrich_alert
from app.triage import triage, write_dossier

RESULT_CONTRACT = "analyst-result-2"

# A model label is a recommendation. "Benign" is not verified as a false positive
# or as authorized activity, so it is recorded as inconclusive (the label itself is
# kept in `verdict`). false_positive / authorized_benign are set only by an analyst
# or a verified playbook.
_DISPOSITION_FOR_VERDICT = {
    "Critical": "malicious",
    "Suspicious": "inconclusive",
    "Benign": "inconclusive",
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provenance_fallback() -> dict[str, Any]:
    """Provenance when no call completed. Never reports a model that did not run."""
    try:
        return CursorAgentProvider().provenance()
    except Exception:  # noqa: BLE001
        return {
            "provider": "cursor-agent",
            "model_selector": None,
            "resolved_model": "unknown",
            "cli_version": "unknown",
            "prompt_version": PROMPT_VERSION,
        }


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

    started_at = _utc()
    llm_verdict: dict[str, Any] | None = None
    llm_meta: dict[str, Any] = {}
    error_category: str | None = None
    error_text: str | None = None
    status = "succeeded"

    try:
        llm_verdict, llm_meta = LLMRouter().triage(prompt)
        audit(
            audit_path,
            "analyst.llm",
            {"alert_id": alert.get("alert_id"), "meta": llm_meta, "verdict": llm_verdict},
        )
    except ProviderError as exc:
        status = "timed_out" if exc.timed_out else "failed"
        error_category = exc.category
        error_text = redact(exc.message, [])[:200]
    except Exception as exc:  # noqa: BLE001 — an unexpected error is still a failure
        status = "failed"
        error_category = "unexpected_error"
        error_text = redact(f"{type(exc).__name__}", [])[:200]

    if status != "succeeded":
        audit(
            audit_path,
            "analyst.llm_failed",
            {
                "alert_id": alert.get("alert_id"),
                "status": status,
                "error_category": error_category,
                "error": error_text,
            },
        )
        llm_meta = _provenance_fallback()

    execution = {
        "status": status,
        "error_category": error_category,
        "error": error_text,
        "started_at": started_at,
        "finished_at": _utc(),
        **{k: llm_meta.get(k) for k in (
            "provider", "model_selector", "resolved_model", "cli_version", "prompt_version", "duration_ms"
        )},
    }

    if status != "succeeded":
        result = {
            "ok": False,
            "contract": RESULT_CONTRACT,
            "alert_id": alert.get("alert_id"),
            "execution": execution,
            "disposition": "unset",
            "verdict": None,
            "llm": None,
            "llm_meta": llm_meta,
            "source_severity": alert.get("severity"),
            "human_review": {"requested": True, "reason": f"investigation_{status}:{error_category}"},
            "limited_evidence": {
                "kind": "local_heuristic",
                "note": (
                    "Local rules only. The model analysis did not complete, so this is not a "
                    "conclusion and cannot support a benign disposition."
                ),
                "heuristic": heuristic,
            },
            "heuristic": heuristic,
            "enrichment": {"local": local, "osint": osint},
            "dossier_id": None,
            "human_soc_effort": "investigation_incomplete_needs_analyst",
        }
        return _finish(result, alert, audit_path)

    verdict = str(llm_verdict.get("verdict"))
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
        "contract": RESULT_CONTRACT,
        "alert_id": alert.get("alert_id"),
        "execution": execution,
        "disposition": _DISPOSITION_FOR_VERDICT.get(verdict, "inconclusive"),
        "verdict": verdict,
        "llm": llm_verdict,
        "llm_meta": llm_meta,
        "source_severity": alert.get("severity"),
        "human_review": {"requested": bool(llm_verdict.get("escalate_to_human")), "reason": "model_requested"},
        "heuristic": heuristic,
        "enrichment": {"local": local, "osint": osint},
        "dossier_id": dossier_id,
        "human_soc_effort": (
            "escalated_for_human_review" if escalate else "recommended_low_touch_not_closed"
        ),
    }
    return _finish(result, alert, audit_path)


def _finish(result: dict[str, Any], alert: dict[str, Any], audit_path: str) -> dict[str, Any]:
    """Push to the control plane (fail-soft) and audit. Failure results are pushed too."""
    raw = alert.get("raw") if isinstance(alert.get("raw"), dict) else {}
    if isinstance(raw.get("tia"), dict):
        # Echo the binding issued by the control plane so both the HTTP reply and
        # the callback identify the exact attempt they answer.
        result["tia_binding"] = {
            k: raw["tia"].get(k) for k in ("attempt_id", "job_id", "evidence_version", "tenant_id", "alert_id")
        }
    try:
        cb = push_triage_result(result, alert)
        if cb is not None:
            result["mssp_callback"] = {"ok": True, "response": cb}
            audit(audit_path, "analyst.callback_ok", {"alert_id": alert.get("alert_id")})
        else:
            result["mssp_callback"] = {"ok": False, "skipped": True}
    except Exception as exc:  # noqa: BLE001
        result["mssp_callback"] = {"ok": False, "error": redact(str(exc), [])[:200]}
        audit(
            audit_path,
            "analyst.callback_failed",
            {"alert_id": alert.get("alert_id"), "error": redact(str(exc), [])[:300]},
        )

    audit(
        audit_path,
        "analyst.complete",
        {
            "alert_id": alert.get("alert_id"),
            "execution_status": (result.get("execution") or {}).get("status"),
            "verdict": result.get("verdict"),
            "dossier_id": result.get("dossier_id"),
        },
    )
    return result
