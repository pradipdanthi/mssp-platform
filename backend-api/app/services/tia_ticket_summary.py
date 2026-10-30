"""Case-specific ticket summary, built only from the stored record.

Facts come from the alert row and stored investigation records, each with its source field. What is
missing is listed. Anything the model said is shown separately as a *hypothesis from a prior
assessment*, with its verdict and confidence, and never as a fact. Nothing here invents a root cause.

The text is deterministic for a given record: the same evidence produces the same summary, which
is what makes a ticket update idempotent (see ``summary_key``).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from app.db.session import fetch_all
from app.services import tia_tools as tools

_DISPOSITION_TEXT = {
    "malicious": "Investigation concluded malicious.",
    "false_positive": "Verified false positive.",
    "authorized_benign": "Verified as authorized activity (not a false positive).",
    "duplicate": "Marked duplicate of another case (a duplicate is not proof the activity is benign).",
    "inconclusive": "Inconclusive: the evidence does not support a conclusion yet.",
    "unset": "No disposition recorded.",
}


def _correlated(scope: tools.Scope, row: Dict[str, Any]) -> List[Dict[str, Any]]:
    clause, params = tools._scoped_clause(scope, "tenant_id")
    rows = fetch_all(
        f"""
        SELECT id::text AS id, lower(severity) AS severity, alert_title AS title, status
        FROM security_alerts
        WHERE id <> %s::uuid{clause}
          AND tenant_id = %s::uuid
          AND created_at > now() - interval '24 hours'
          AND ((%s::text IS NOT NULL AND destination_host = %s)
            OR (%s::text IS NOT NULL AND source_ip = %s::inet))
        ORDER BY created_at DESC LIMIT 10;
        """,
        (row["id"], *params, row["tenant_id"], row.get("host"), row.get("host"), row.get("source_ip"), row.get("source_ip")),
    )
    return [dict(r) for r in rows or []]


def build(scope: tools.Scope, alert_id: str) -> Dict[str, Any]:
    tools.authorize("explain_evidence", scope)
    ev = tools.explain_evidence(scope, alert_id)
    row = tools.get_alert_row(scope, alert_id)
    if not row:
        raise tools.ToolError("not_found", "I can't find that alert in this scope.")
    inv = ev["investigation"]
    result = (inv.get("latest_result") or {}) if inv.get("available") else {}
    disposition = result.get("disposition") or "unset"
    related = _correlated(scope, row)

    facts = [f"{p['field']}: {p['value']}" for p in ev["present"]]
    facts.insert(0, f"{row['severity']} alert from {row['source_tool']} at {row.get('event_time') or 'unknown time'}: {row['title']}")
    unknowns = [f"No {m} in the stored record." for m in ev["missing"]]
    if related:
        facts.append(f"{len(related)} other alert(s) on the same host or source in the last 24 hours: " + "; ".join(f"[{r['severity']}] {r['title']} ({r['status']})" for r in related[:5]))

    hypotheses: List[str] = []
    prior = ev["prior_ai_assessment"]
    if prior.get("verdict"):
        hypotheses.append(f"A prior automated assessment returned '{prior['verdict']}'" + (f" with confidence {prior['confidence']}" if prior.get("confidence") is not None else "") + ". This is a recommendation, not a finding.")
    if prior.get("attack_type"):
        hypotheses.append(f"Suggested attack type: {prior['attack_type']} (unverified).")

    if not inv.get("available"):
        state = "Investigation records are unavailable; this summary uses the alert record only."
    elif result:
        state = f"Latest investigation: {result.get('execution_status')}" + (f" ({result['error_category']})" if result.get("error_category") else "") + f", accepted {result.get('accepted_at')}."
    else:
        state = "No investigation has completed for this alert."
    review = inv.get("review_item") if inv.get("available") else None

    if disposition == "malicious" or row["severity"] == "critical" and disposition in ("unset", "inconclusive"):
        next_step = "Analyst review now. Any containment needs human approval in Needs You."
    elif review:
        next_step = f"Open review item ({review.get('reason_code')}, priority {review.get('assessed_priority')}); due {review.get('due_at')}."
    elif disposition in ("false_positive", "authorized_benign", "duplicate"):
        next_step = "No action unless contradicting evidence appears."
    else:
        next_step = "Analyst triage; evidence above is what is on record."

    body = {
        "headline": f"[{row['severity'].upper()}] {row['title']} on {row.get('host') or 'unknown host'} ({row['short_code']})",
        "facts": facts,
        "not_known": unknowns,
        "hypotheses": hypotheses,
        "investigation": state,
        "disposition": {"value": disposition, "meaning": _DISPOSITION_TEXT.get(disposition, _DISPOSITION_TEXT["unset"])},
        "next_step": next_step,
    }
    body["summary_key"] = summary_key(row["id"], body)
    body["text"] = render(body)
    return body


def summary_key(alert_id: str, body: Dict[str, Any]) -> str:
    stable = {k: body[k] for k in ("headline", "facts", "not_known", "hypotheses", "investigation", "disposition", "next_step")}
    return hashlib.sha256((alert_id + json.dumps(stable, sort_keys=True)).encode()).hexdigest()[:24]


def render(body: Dict[str, Any]) -> str:
    def block(title: str, items: List[str]) -> str:
        return f"{title}\n" + ("\n".join(f"- {i}" for i in items) if items else "- none") + "\n"

    return (
        f"{body['headline']}\n\n"
        + block("Known (from the stored record)", body["facts"])
        + "\n"
        + block("Not known", body["not_known"])
        + "\n"
        + block("Hypotheses (unverified)", body["hypotheses"])
        + f"\nInvestigation: {body['investigation']}\nDisposition: {body['disposition']['meaning']}\nNext step: {body['next_step']}\n"
    )
