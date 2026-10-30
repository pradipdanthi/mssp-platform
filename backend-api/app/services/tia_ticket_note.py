"""Write TIA's investigation into the ticket analysts actually work: the incident timeline.

Analysts read and maintain case history on the SOC console incident page (Timeline and
Comments, backed by ``incident_timeline`` / ``incident_comments``). The control plane holds no
TheHive case ids, and the TheHive integration account sees no cases, so TheHive is not the
working ticket for these alerts; no TheHive write is made from here.

One note per alert and evidence version (tia_effects). A retry or a second worker finds the
committed note instead of adding another. New evidence (a new evidence version) is a new note.
The note never changes an incident's status, owner or resolution: those are human decisions.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

from app.db.session import fetch_all, fetch_one
from app.services import tia_effects, tia_evidence
from app.services import tia_tools as tools

logger = logging.getLogger(__name__)

NOTE_TITLE = "TIA investigation note"


def incident_for_alert(tenant_id: str, alert_id: str) -> Optional[Dict[str, Any]]:
    return fetch_one(
        """
        SELECT i.id::text AS id, i.incident_number, i.status, i.assigned_to_user_id::text AS assigned_to
        FROM incidents i
        WHERE i.tenant_id = %s::uuid
          AND (i.primary_alert_id = %s::uuid
               OR EXISTS (SELECT 1 FROM incident_alerts ia WHERE ia.incident_id = i.id AND ia.alert_id = %s::uuid))
        ORDER BY (i.primary_alert_id = %s::uuid) DESC, i.created_at DESC LIMIT 1;
        """,
        (tenant_id, alert_id, alert_id, alert_id),
    ) or None


def _attempt(attempt_id: str) -> Dict[str, Any]:
    return fetch_one(
        "SELECT a.id::text AS id, a.tenant_id::text AS tenant_id, a.alert_id::text AS alert_id, a.evidence_version, a.attempt_no, "
        "a.evidence_manifest, (a.dispatched_at AT TIME ZONE 'utc')::text AS dispatched_at, "
        "r.execution_status, r.error_category, r.verdict, r.confidence::float AS confidence, r.disposition, r.outcome, r.provenance, "
        "(r.accepted_at AT TIME ZONE 'utc')::text AS accepted_at "
        "FROM tia_investigation_attempts a LEFT JOIN tia_results r ON r.attempt_id = a.id WHERE a.id = %s::uuid;",
        (attempt_id,),
    ) or {}


def compose(attempt_id: str) -> Dict[str, Any]:
    """The note body: confirmed facts, supported hypotheses, unresolved cause, what was checked."""
    from app.services import tia_ticket_summary

    att = _attempt(attempt_id)
    if not att:
        raise LookupError("attempt not found")
    scope = tools.Scope(operator_email="tia", operator_id=None, role="platform_admin", session_id="ticket-note", tenant_id=att["tenant_id"])
    summary = tia_ticket_summary.build(scope, att["alert_id"])
    outcome = att.get("outcome") or {}
    llm = (outcome.get("llm") or {}) if att.get("execution_status") == "succeeded" else {}
    manifest = att.get("evidence_manifest") or {}

    checked: List[str] = []
    gaps: List[str] = []
    for name, sec in (manifest.get("sections") or {}).items():
        label = name.replace("_", " ")
        status = sec.get("status")
        if status == "present":
            checked.append(f"{label}: {sec.get('items')} item(s) from {sec.get('source')}")
        elif status == "empty":
            checked.append(f"{label}: checked, nothing found ({sec.get('note') or sec.get('source')})")
        elif status == "unavailable":
            gaps.append(f"{label}: source unavailable, so its absence proves nothing ({sec.get('note') or ''})".rstrip(" ()"))
        else:
            gaps.append(f"{label}: no such source ({sec.get('note') or 'not configured'})")
        for m in sec.get("missing") or []:
            gaps.append(f"{label}: missing {m}")
    if manifest.get("sent_form") == "redacted":
        gaps.append("the model saw a redacted dossier (no customer authorisation for full context)")

    research = (tia_evidence._research({"id": att["alert_id"], "tenant_id": att["tenant_id"]}).get("items") or []) if manifest else []

    hypotheses = list(summary["hypotheses"])
    if llm.get("summary"):
        # The alert's stored AI verdict is this attempt's own result once accepted; do not count it twice.
        hypotheses = [h for h in hypotheses if not h.startswith("A prior automated assessment")]
        hypotheses.append(f"TIA model assessment ({att.get('verdict')}, confidence {att.get('confidence'):.0f}%): {llm['summary'][:800]} (a model view, not a finding)")
    if llm.get("root_cause"):
        hypotheses.append(f"Proposed cause, unverified: {llm['root_cause'][:500]}")

    if att.get("execution_status") != "succeeded":
        state = f"The investigation did not complete ({att.get('execution_status') or 'no result'}: {att.get('error_category') or 'unknown'}). No verdict."
        unresolved = "Cause not established: the investigation did not complete."
    elif att.get("disposition") in ("malicious", "false_positive", "authorized_benign"):
        state = f"Investigation finished; disposition {att['disposition']}."
        unresolved = "None recorded." if att["disposition"] != "malicious" else "Scope and entry point still need analyst confirmation."
    else:
        state = f"Investigation finished; verdict {att.get('verdict')} is unverified until an analyst confirms it."
        unresolved = "Cause not established. The hypotheses above are unverified."

    lines = [
        summary["headline"],
        "",
        "Confirmed (from the stored record):",
        *([f"- {f}" for f in summary["facts"]] or ["- none"]),
        "",
        "Supported hypotheses (unverified):",
        *([f"- {h}" for h in hypotheses] or ["- none"]),
        "",
        f"Unresolved: {unresolved}",
        "",
        "What TIA checked:",
        *([f"- {c}" for c in checked] or ["- no evidence manifest was recorded for this attempt"]),
        "",
        "Gaps:",
        *([f"- {g}" for g in (gaps if manifest else summary["not_known"])] or ["- none"]),
    ]
    if research:
        lines += ["", "External research:"] + [
            f"- {r['provider']} '{r['query_text']}': {r['result']}" + (f", {r['source_url']} fetched {r['fetched_at']}" if r.get("http_status") == 200 else "")
            for r in research
        ]
    lines += [
        "",
        f"Investigation: {state}",
        f"Next step: {summary['next_step']}",
        f"Record: attempt {att['attempt_no']} ({att['id']}), evidence version {att['evidence_version']}, dossier {manifest.get('dossier_hash', 'none')[:12]}, policy tia-closure-1.",
    ]
    text = "\n".join(lines)
    return {"attempt": att, "text": text, "content_hash": hashlib.sha256(text.encode()).hexdigest()}


def write_investigation_note(attempt_id: str) -> Dict[str, Any]:
    note = compose(attempt_id)
    att = note["attempt"]
    inc = incident_for_alert(att["tenant_id"], att["alert_id"])
    if not inc:
        return tia_effects.skip(kind="ticket_note", tenant_id=att["tenant_id"], alert_id=att["alert_id"],
                                evidence_version=att["evidence_version"], attempt_id=attempt_id, reason="no_incident_for_alert")
    human_closed = inc["status"] in ("resolved", "closed")
    text = note["text"] + ("\n(Added after an analyst resolved this incident; the incident status was not changed.)" if human_closed else "")

    def write(cur) -> str:
        cur.execute(
            "INSERT INTO incident_timeline (incident_id, event_type, visibility, title, details) "
            "VALUES (%s::uuid, 'comment', 'internal', %s, %s) RETURNING id::text AS id;",
            (inc["id"], NOTE_TITLE, text),
        )
        return str(cur.fetchone()["id"])

    out = tia_effects.apply_local(
        kind="ticket_note", tenant_id=att["tenant_id"], alert_id=att["alert_id"], incident_id=inc["id"],
        evidence_version=att["evidence_version"], attempt_id=attempt_id, content_hash=note["content_hash"], write=write,
    )
    out["incident_id"] = inc["id"]
    out["incident_number"] = inc["incident_number"]
    if out["outcome"] == "committed":
        out["verified"] = verify(out["effect_id"], inc["id"], out["target_ref"], note["content_hash"], text)
    return out


def verify(effect_id: str, incident_id: str, timeline_id: str, content_hash: str, text: str) -> bool:
    """Read the note back the way the incident page does, then stamp the ledger."""
    from app.db.session import execute

    row = fetch_one(
        "SELECT details FROM incident_timeline WHERE id = %s::uuid AND incident_id = %s::uuid AND title = %s;",
        (timeline_id, incident_id, NOTE_TITLE),
    )
    ok = bool(row) and row.get("details") == text
    if ok:
        execute("UPDATE tia_effects SET verified_at = now() WHERE id = %s::uuid;", (effect_id,))
    return ok


def after_acceptance(attempt_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Best effort: a ticket note failure never undoes the accepted investigation."""
    if not attempt_id:
        return None
    try:
        return write_investigation_note(attempt_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ticket note not written attempt=%s: %s", attempt_id, type(exc).__name__)
        return {"outcome": "error", "error": type(exc).__name__}

