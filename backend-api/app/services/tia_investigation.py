"""TIA investigation outcome handling (repair increment 1).

Separates four things that used to be conflated:

  execution status   what happened to the call:
                     succeeded | degraded | failed | timed_out
  disposition        what a validated analysis recommends:
                     malicious | inconclusive | unset
                     (false_positive / authorized_benign are never set here)
  severity / priority  source severity is kept as received; assessed priority is
                     computed by policy from severity and asset tier only
  review vs page     whether a person must look (durable review item) is
                     separate from whether to wake someone (notification)

Rules enforced here:
  * A failed, timed-out, malformed, empty, or incomplete result never yields a
    verdict, never a benign one, and never suppresses escalation.
  * The model can ask for more review. It cannot suppress a required review and
    cannot choose notification destinations (unknown keys are dropped).
  * Degradation comes from explicit execution status, not model-name text.
  * Every non-success outcome becomes a durable review item (idempotent).

The first half of this module is pure (no database). The second half writes the
review item and reads the queue.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CONTRACT = "analyst-result-2"
POLICY_VERSION = "tia-review-1"

EXECUTION_STATUSES = ("succeeded", "degraded", "failed", "timed_out")

# Categories the agent emits plus those this control plane adds.
KNOWN_ERROR_CATEGORIES = frozenset(
    {
        "not_configured",
        "binary_missing",
        "auth_failure",
        "timeout",
        "nonzero_exit",
        "empty_output",
        "malformed_output",
        "missing_fields",
        "unexpected_error",
        "agent_unreachable",
        "agent_http_error",
        "agent_bad_response",
        "agent_disabled",
        "invalid_agent_result",
        "legacy_heuristic_fallback",
        "fallback_rule_based",
        "manual_review_mode",
        "sandbox_blocked",
        "runner_unavailable",
        "runner_busy",
        "prompt_too_large",
    }
)

# Failures that point at the provider or its credentials rather than one alert.
# Their non-urgent notifications are de-duplicated; the cases themselves are not.
PROVIDER_WIDE_CATEGORIES = frozenset(
    {
        "auth_failure", "binary_missing", "not_configured", "agent_unreachable", "agent_http_error",
        "sandbox_blocked", "runner_unavailable",
    }
)

# Retrying cannot help until a person fixes configuration or credentials.
NON_RETRYABLE_CATEGORIES = frozenset(
    {"auth_failure", "binary_missing", "not_configured", "agent_disabled", "sandbox_blocked", "prompt_too_large"}
)

_SEVERITY_RANKS = {"low": 1, "medium": 2, "high": 3, "critical": 4}

_VERDICT_MAP = {
    "critical": "MALICIOUS",
    "malicious": "MALICIOUS",
    "suspicious": "SUSPICIOUS",
    "benign": "BENIGN_FALSE_POSITIVE",
}

# A model "Benign" is not verified as false positive or authorized activity.
_DISPOSITION_FOR_DB_VERDICT = {
    "MALICIOUS": "malicious",
    "SUSPICIOUS": "inconclusive",
    "BENIGN_FALSE_POSITIVE": "inconclusive",
}

_UNKNOWN_MODEL_SELECTORS = frozenset({"", "account_default", "default", "auto", "unknown", "none"})

# Deadlines are POLICY INPUTS that the SOC owner has not approved yet. The values
# below are conservative placeholders, overridable by environment, and are listed
# as an open prerequisite in docs/TIA_INVESTIGATION_STATUS.md.
_DEFAULT_DUE_MINUTES = {"critical": 15, "high": 60, "medium": 240, "low": 1440, "unknown": 60}


# --------------------------------------------------------------------------
# Normalisation (pure)
# --------------------------------------------------------------------------


@dataclass
class Outcome:
    execution_status: str
    error_category: Optional[str] = None
    error: Optional[str] = None
    disposition: str = "unset"
    llm: Optional[Dict[str, Any]] = None  # validated, whitelisted; None unless succeeded
    verdict_db: Optional[str] = None
    confidence: Optional[float] = None
    model_review_requested: bool = False
    source_severity: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)
    limited_evidence: Dict[str, Any] = field(default_factory=dict)
    dossier_id: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.execution_status == "succeeded"


def _clean_selector(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return None if text.lower() in _UNKNOWN_MODEL_SELECTORS else text[:120]


def _strict_bool(value: Any) -> bool:
    return value is True


def validate_llm(raw: Any) -> Optional[Dict[str, Any]]:
    """Server-side re-validation of the analysis block. None when unusable.

    Never trusts the agent's own validation and never invents defaults: a missing
    verdict, a non-numeric confidence, or an empty summary is a failure.
    """
    if not isinstance(raw, dict):
        return None
    label = str(raw.get("verdict") or "").strip().lower().replace(" ", "_")
    if label not in _VERDICT_MAP:
        return None
    conf = raw.get("confidence")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        return None
    if not 0.0 <= float(conf) <= 100.0:
        return None
    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None

    pkg_in = raw.get("action_package") if isinstance(raw.get("action_package"), dict) else {}
    pkg = {
        key: _strict_bool(pkg_in.get(key))
        for key in (
            "propose_edr_isolate",
            "propose_itdr_remediate",
            "propose_case_note",
            "propose_customer_recommendation",
            "escalate_human",
        )
    }
    for key in ("customer_action_title", "customer_action_body", "notes"):
        if isinstance(pkg_in.get(key), str):
            pkg[key] = pkg_in[key][:4000]

    actions = raw.get("recommended_actions")
    mitre = raw.get("mitre")
    return {
        "verdict": {"critical": "Critical", "malicious": "Critical", "suspicious": "Suspicious", "benign": "Benign"}[label],
        "confidence": float(conf),
        "summary": summary.strip()[:4000],
        "customer_safe_summary": str(raw.get("customer_safe_summary") or "")[:2000],
        "root_cause": str(raw.get("root_cause") or "")[:2000],
        "mitre": [m for m in mitre if isinstance(m, dict)][:12] if isinstance(mitre, list) else [],
        "recommended_actions": [str(a)[:500] for a in actions][:12] if isinstance(actions, list) else [],
        "false_positive_likelihood": raw.get("false_positive_likelihood")
        if isinstance(raw.get("false_positive_likelihood"), (int, float))
        and not isinstance(raw.get("false_positive_likelihood"), bool)
        else None,
        "escalate_to_human": _strict_bool(raw.get("escalate_to_human")),
        "action_package": pkg,
    }


def _provenance(raw: Dict[str, Any], execution: Dict[str, Any], *, contract: str, source: str) -> Dict[str, Any]:
    meta = raw.get("llm_meta") if isinstance(raw.get("llm_meta"), dict) else {}
    selector = execution.get("model_selector", meta.get("model_selector", meta.get("model")))
    return {
        "provider": str(execution.get("provider") or meta.get("provider") or "unknown")[:60],
        "model_selector": _clean_selector(selector),
        # Cursor does not report the model that actually answered. Do not guess.
        "resolved_model": "unknown",
        "cli_version": str(execution.get("cli_version") or meta.get("cli_version") or "unknown")[:60],
        "prompt_version": str(execution.get("prompt_version") or meta.get("prompt_version") or "unknown")[:60],
        "contract": contract,
        "source": source,
        "started_at": execution.get("started_at"),
        "finished_at": execution.get("finished_at"),
        "duration_ms": execution.get("duration_ms") if isinstance(execution.get("duration_ms"), int) else None,
        "policy_version": POLICY_VERSION,
    }


def _failure(
    status: str,
    category: str,
    *,
    error: Optional[str] = None,
    provenance: Optional[Dict[str, Any]] = None,
    limited: Optional[Dict[str, Any]] = None,
    source_severity: Optional[str] = None,
) -> Outcome:
    if status not in EXECUTION_STATUSES or status == "succeeded":
        status = "failed"
    if category not in KNOWN_ERROR_CATEGORIES:
        category = "unexpected_error"
    prov = dict(provenance or {})
    prov["error_category"] = category
    prov.setdefault("policy_version", POLICY_VERSION)
    return Outcome(
        execution_status=status,
        error_category=category,
        error=(error or "")[:300] or None,
        disposition="unset",
        provenance=prov,
        limited_evidence=limited or {},
        model_review_requested=True,
        source_severity=source_severity,
    )


def transport_failure(category: str, *, timed_out: bool = False, error: Optional[str] = None, source_severity: Optional[str] = None) -> Outcome:
    """The agent could not be reached or answered with an unusable HTTP response."""
    return _failure(
        "timed_out" if timed_out else "failed",
        "timeout" if timed_out else category,
        error=error,
        provenance={"provider": "cursor-agent", "resolved_model": "unknown", "model_selector": None, "contract": CONTRACT, "source": "agent_http"},
        source_severity=source_severity,
    )


def normalize_agent_result(raw: Any, *, source: str, source_severity: Optional[str] = None) -> Outcome:
    """Turn an agent result (HTTP reply or callback body) into a validated Outcome.

    ``source_severity`` is the severity stored on the alert (server-side). The
    agent's copy is used only when the server value is unavailable.
    """
    if not isinstance(raw, dict):
        return _failure("failed", "agent_bad_response", source_severity=source_severity)

    sev = source_severity or (str(raw.get("source_severity") or "").strip().lower() or None)
    execution = raw.get("execution") if isinstance(raw.get("execution"), dict) else None
    limited = raw.get("limited_evidence") if isinstance(raw.get("limited_evidence"), dict) else {}

    if execution is None:
        # Legacy agent (pre analyst-result-2). Detect the old heuristic fallback
        # explicitly, then require a fully valid analysis like any other result.
        meta = raw.get("llm_meta") if isinstance(raw.get("llm_meta"), dict) else {}
        llm_in = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
        provider = str(meta.get("provider") or "")
        if provider.startswith("heuristic_fallback") or llm_in.get("root_cause") == "cursor_llm_error":
            return _failure(
                "failed",
                "legacy_heuristic_fallback",
                provenance=_provenance(raw, {}, contract="legacy", source=source),
                limited={"kind": "local_heuristic", "note": "Legacy agent substituted local rules for a failed model call."},
                source_severity=sev,
            )
        if raw.get("ok") is not True:
            return _failure("failed", "invalid_agent_result", provenance=_provenance(raw, {}, contract="legacy", source=source), source_severity=sev)
        execution = {}
        contract = "legacy"
    else:
        contract = str(raw.get("contract") or CONTRACT)
        status = str(execution.get("status") or "")
        if status in ("failed", "timed_out", "degraded"):
            category = str(execution.get("error_category") or "unexpected_error")
            return _failure(
                status,
                category,
                error=str(execution.get("error") or "") or None,
                provenance=_provenance(raw, execution, contract=contract, source=source),
                limited=limited,
                source_severity=sev,
            )
        if status != "succeeded" or raw.get("ok") is not True:
            return _failure(
                "failed",
                "invalid_agent_result",
                provenance=_provenance(raw, execution, contract=contract, source=source),
                limited=limited,
                source_severity=sev,
            )

    llm = validate_llm(raw.get("llm"))
    if llm is None:
        return _failure(
            "failed",
            "invalid_agent_result",
            error="analysis block missing or invalid",
            provenance=_provenance(raw, execution, contract=contract, source=source),
            limited=limited,
            source_severity=sev,
        )

    verdict_db = _VERDICT_MAP[llm["verdict"].lower()]
    pkg = llm["action_package"]
    return Outcome(
        execution_status="succeeded",
        disposition=_DISPOSITION_FOR_DB_VERDICT[verdict_db],
        llm=llm,
        verdict_db=verdict_db,
        confidence=llm["confidence"],
        model_review_requested=bool(llm["escalate_to_human"] or pkg.get("escalate_human")),
        source_severity=sev,
        provenance=_provenance(raw, execution, contract=contract, source=source),
        limited_evidence=limited,
        dossier_id=str(raw.get("dossier_id")) if raw.get("dossier_id") else None,
    )


# --------------------------------------------------------------------------
# Review / paging decision (pure)
# --------------------------------------------------------------------------


def escalate_floor() -> float:
    """Confidence floor (0-100) for waking a human on a MALICIOUS verdict."""
    try:
        return float(os.getenv("AI_DEEP_TRIAGE_ESCALATE_CONFIDENCE") or "60")
    except ValueError:
        return 60.0


def benign_silence_floor() -> float:
    """A BENIGN verdict on a critical alert stays silent only at or above this."""
    try:
        return float(os.getenv("AI_DEEP_TRIAGE_BENIGN_SILENCE_CONFIDENCE") or "85")
    except ValueError:
        return 85.0


def investigation_mode() -> str:
    """'normal', or 'manual_review' (the documented safe rollback mode).

    In manual_review no model is called. Every qualifying alert becomes an analyst
    review item with the same paging rules, and no verdict is ever produced, so the
    known false-benign behavior cannot return through a rollback.
    """
    raw = (os.getenv("TIA_INVESTIGATION_MODE") or "normal").strip().lower()
    return "manual_review" if raw == "manual_review" else "normal"


def _due_minutes(sev: str) -> int:
    env_name = f"TIA_REVIEW_DUE_MINUTES_{sev.upper()}"
    try:
        value = int(os.getenv(env_name) or _DEFAULT_DUE_MINUTES.get(sev, _DEFAULT_DUE_MINUTES["unknown"]))
    except ValueError:
        value = _DEFAULT_DUE_MINUTES.get(sev, _DEFAULT_DUE_MINUTES["unknown"])
    return max(1, min(value, 7 * 24 * 60))


def decide_review(
    *,
    source_severity: Optional[str],
    asset_criticality: Optional[str],
    execution_status: str,
    error_category: Optional[str] = None,
    verdict: Optional[str] = None,
    confidence: float = 0.0,
    recommended_action: Optional[str] = None,
    model_review_requested: bool = False,
    escalate_floor: float = 60.0,
    benign_silence_floor: float = 85.0,
) -> Dict[str, Any]:
    """Fixed rules only. The model supplies a verdict; it never sets the outcome.

    Returns review_required / page / urgency / due_minutes / assessed_priority /
    reasons / reason_code. ``page`` is computed from policy inputs alone: the
    model cannot clear it, and nothing it returns selects a destination.
    """
    sev = (source_severity or "").strip().lower()
    rank = _SEVERITY_RANKS.get(sev, 0)
    tier = (asset_criticality or "").strip().lower()
    verdict_u = (verdict or "").strip().upper()
    action_u = (recommended_action or "").strip().upper()
    try:
        conf = float(confidence or 0.0)
    except (TypeError, ValueError):
        conf = 0.0

    critical = rank >= _SEVERITY_RANKS["critical"]
    urgent = critical or (rank >= _SEVERITY_RANKS["high"] and tier == "critical")
    succeeded = execution_status == "succeeded"

    reasons: List[str] = []
    page = False
    urgency = "normal"
    required = False
    reason_code: Optional[str] = None

    def positive_findings() -> None:
        nonlocal page, urgency
        if verdict_u == "MALICIOUS" and conf >= escalate_floor:
            page = True
            urgency = "high"
            reasons.append(f"AI verdict MALICIOUS at {conf:.0f}% confidence")
        if action_u == "ISOLATE_AGENT":
            page = True
            urgency = "high"
            reasons.append("AI recommends host isolation — needs human approval")
        if verdict_u == "SUSPICIOUS" and critical:
            page = True
            reasons.append("Suspicious verdict on a critical-severity alert")
        if page and tier in ("critical", "high"):
            urgency = "high"
            reasons.append(f"Asset criticality is {tier}")

    if not succeeded:
        # No trustworthy analysis. Fail toward the human; never toward benign.
        required = True
        status_label = execution_status if execution_status in EXECUTION_STATUSES else "failed"
        reason_code = f"investigation_{status_label}"
        reasons.append(
            f"Investigation {status_label.replace('_', ' ')}"
            + (f" ({error_category})" if error_category else "")
            + " — no analysis available; analyst review required"
        )
        if urgent:
            page = True
            urgency = "high"
            reasons.append("Urgent alert: analysis unavailable, paging a human")
        if status_label == "degraded":
            # Limited evidence may still raise a concern, but a benign reading
            # from limited evidence is discarded.
            positive_findings()
    else:
        positive_findings()
        if verdict_u == "BENIGN_FALSE_POSITIVE" and action_u != "ISOLATE_AGENT":
            if critical and conf < benign_silence_floor:
                page = True
                urgency = "normal"
                reasons = [
                    f"AI leans benign at {conf:.0f}% on a critical alert — "
                    f"below the {benign_silence_floor:.0f}% bar to stay silent; human confirms"
                ]
                required = True
                reason_code = "policy_required"
            else:
                page = False
                urgency = "normal"
                reasons = ["AI assessed benign — recommendation only, no human wake"]

    if model_review_requested:
        required = True
        reason_code = reason_code or "model_requested_review"
        reasons.append("Analysis asked for analyst review")
    if page:
        required = True
        reason_code = reason_code or "policy_required"

    if urgent:
        priority = "P1"
    elif page:
        priority = "P2"
    else:
        priority = {3: "P2", 2: "P3", 1: "P4"}.get(rank, "P3")

    due = _due_minutes(sev if sev in _DEFAULT_DUE_MINUTES else "unknown")
    if page:
        due = min(due, 60)

    return {
        "escalate": page,
        "review_required": required,
        "urgency": urgency,
        "reasons": reasons,
        "reason_code": reason_code,
        "execution_status": execution_status,
        "error_category": error_category,
        "source_severity": sev or None,
        "assessed_priority": priority,
        "due_minutes": due,
        "verdict": verdict_u or None,
        "confidence": conf,
        "recommended_action": action_u or None,
        "degraded": not succeeded,
        "policy_version": POLICY_VERSION,
    }


# --------------------------------------------------------------------------
# Review summary (database). Review items are written only by tia_acceptance.
# --------------------------------------------------------------------------


def open_review_summary(tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """Counts for the SOC console. Table may not exist before the migration."""
    from app.db.session import fetch_one

    try:
        row = fetch_one(
            """
            SELECT
              count(*) FILTER (WHERE status <> 'resolved')::int AS open_count,
              count(*) FILTER (WHERE status <> 'resolved' AND due_at < now())::int AS overdue_count,
              count(*) FILTER (WHERE status <> 'resolved' AND notify_urgency = 'page')::int AS page_count,
              count(*) FILTER (WHERE status <> 'resolved' AND notification_state IN ('no_recipients_configured', 'page_failed'))::int AS undeliverable_page_count,
              min(due_at) FILTER (WHERE status <> 'resolved') AS next_due_at
            FROM tia_review_items
            WHERE (%s::uuid IS NULL OR tenant_id = %s::uuid);
            """,
            (tenant_id, tenant_id),
        )
    except Exception:  # noqa: BLE001
        logger.warning("tia_review_items unavailable (migration not applied?)")
        return {"available": False}
    data = dict(row or {})
    data["available"] = True
    if data.get("next_due_at") is not None:
        data["next_due_at"] = str(data["next_due_at"])
    return data
