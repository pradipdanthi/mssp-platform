"""Verified playbooks: the only unattended path to closing an alert.

A model "Benign" is a recommendation and is never enough (policy tia-closure-1). A playbook is a
versioned, deterministic rule evaluated over STORED evidence, enabled per tenant by a human who
records the customer's authorisation. With no enablement row, every evaluation is shadow-only
and nothing is closed. Production ships with no enablement rows.

Playbook ``authorized_scanner`` v1 closes a low-to-high severity scanner-family alert as
``authorized_benign`` (status ``closed``; NOT ``false_positive``, because the activity was real and approved) only when ALL hold, read from the database, never from model text:

  1. the source address is covered by a live, unrevoked, approved authorised-activity record
     (approver, change reference, validity window) for the SAME tenant;
  2. the alert's own rule family is a scanner/discovery family, not an exploit or post-compromise one;
  3. severity is not critical;
  4. required evidence is present (source address, event time);
  5. no correlated evidence contradicts it: no other open high/critical alert in the same tenant
     in the last 24 h touching the same host or source with a non-scanner family, and no accepted
     TIA investigation result marking the alert malicious.

Outcomes: ``close`` (all hold), ``refuse`` (not eligible, e.g. an unapproved source), ``review``
(evidence missing or contradictory: a human decides). Each evaluation is recorded; closure is
idempotent, re-checks the evidence immediately before writing, verifies the write by reading it
back, and can be reversed by ``reconcile`` when contradicting evidence arrives later.

This is delivery-at-least-once safe: evaluation rows are unique per (alert, playbook, version,
evidence hash) and a closure runs once.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.db.session import db_transaction, fetch_all, fetch_one
from app.services.tia_closure_policy import PlaybookVerdict, authorize_ticket_action

logger = logging.getLogger(__name__)

PLAYBOOK_ID = "authorized_scanner"
PLAYBOOK_VERSION = 1
DISPOSITION = "authorized_benign"  # approved activity is NOT a false positive; the two stay distinct
TARGET_STATUS = "closed"
RESOLUTION_LABEL = "Closed (verified playbook: authorized scanner v1)"
TERMINAL = ("closed", "false_positive", "resolved")

_SCANNER_FAMILY = re.compile(r"\b(port ?scan|network scan|vulnerability scan|vuln scan|scanner|nmap|nessus|openvas|nuclei|host discovery|ping sweep|service enumeration)\b", re.I)
_NOT_SCANNER = re.compile(
    r"\b(exploit|shell|ransom|credential|mimikatz|malware|trojan|c2|beacon|exfil|brute ?force|privilege|persistence|lateral|"
    r"webshell|dump|injection|rce|backdoor|encrypt)\b",
    re.I,
)


def schema_ready() -> bool:
    try:
        return bool(fetch_one("SELECT to_regclass('public.tia_playbook_evaluations') IS NOT NULL AS ok;").get("ok"))
    except Exception:  # noqa: BLE001
        return False


def _is_scanner_family(title: str) -> bool:
    return bool(_SCANNER_FAMILY.search(title or "")) and not _NOT_SCANNER.search(title or "")


def _load_alert(alert_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    return fetch_one(
        "SELECT id::text AS id, tenant_id::text AS tenant_id, severity, alert_title, source_ip::text AS source_ip, "
        "destination_ip::text AS destination_ip, destination_host, status, event_time, created_at "
        "FROM security_alerts WHERE id = %s::uuid AND tenant_id = %s::uuid;",
        (alert_id, tenant_id),
    ) or None


def _authorizations(tenant_id: str, source_ip: str, at: Any) -> List[Dict[str, Any]]:
    return fetch_all(
        "SELECT id::text AS id, label, approved_by, reference, destination_cidr::text AS destination_cidr, destination_host "
        "FROM tia_authorized_activity "
        "WHERE tenant_id = %s::uuid AND kind = 'scanner' AND source_ip = %s::inet AND revoked_at IS NULL "
        "AND valid_from <= %s AND valid_to >= %s ORDER BY created_at;",
        (tenant_id, source_ip, at, at),
    ) or []


def _in_cidr(addr: Optional[str], cidr: str) -> bool:
    if not addr:
        return False
    try:
        import ipaddress
        return ipaddress.ip_address(addr) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def _auth_covers_destination(auth: Dict[str, Any], alert: Dict[str, Any]) -> bool:
    """NULL destination on the approval means any destination. A named scope must match."""
    cidr, host = (auth.get("destination_cidr") or "").strip(), (auth.get("destination_host") or "").strip().lower()
    if not cidr and not host:
        return True
    dest_ip, dest_host = alert.get("destination_ip"), (alert.get("destination_host") or "").strip().lower()
    if host and dest_host == host:
        return True
    if cidr and (_in_cidr(dest_ip, cidr) or _in_cidr(dest_host, cidr)):
        return True
    return False


def _contradictions(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Distinguish 'queried and found none' from 'could not query'. Absence of a result is not proof of absence."""
    try:
        rows = fetch_all(
            "SELECT id::text AS id, severity, alert_title, status FROM security_alerts "
            "WHERE tenant_id = %s::uuid AND id <> %s::uuid AND lower(severity) IN ('critical','high') "
            "AND status NOT IN ('closed','false_positive','resolved') "
            "AND created_at > now() - interval '24 hours' "
            "AND ((%s::text IS NOT NULL AND destination_host = %s) OR (%s::text IS NOT NULL AND source_ip = %s::inet)) "
            "ORDER BY created_at DESC LIMIT 20;",
            (alert["tenant_id"], alert["id"], alert["destination_host"], alert["destination_host"], alert["source_ip"], alert["source_ip"]),
        ) or []
        items = [r for r in rows if not _is_scanner_family(str(r.get("alert_title") or ""))]
        return {"status": "present" if items else "empty", "items": items}
    except Exception as exc:  # noqa: BLE001
        logger.warning("correlation query unavailable: %s", type(exc).__name__)
        return {"status": "unavailable", "items": [], "note": type(exc).__name__}


def _incident_siblings(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Other unresolved high/critical non-scanner alerts on the same incident. Closing this alert must not close the incident."""
    try:
        rows = fetch_all(
            """
            SELECT sa.id::text AS id, sa.severity, sa.alert_title, sa.status, i.id::text AS incident_id, i.incident_number, i.status AS incident_status
            FROM incidents i
            JOIN incident_alerts ia ON ia.incident_id = i.id
            JOIN security_alerts sa ON sa.id = ia.alert_id
            WHERE i.tenant_id = %s::uuid
              AND i.id IN (
                    SELECT incident_id FROM incident_alerts WHERE alert_id = %s::uuid
                    UNION SELECT id FROM incidents WHERE primary_alert_id = %s::uuid
              )
              AND sa.id <> %s::uuid
              AND lower(sa.severity) IN ('critical','high')
              AND sa.status NOT IN ('closed','false_positive','resolved')
            LIMIT 20;
            """,
            (alert["tenant_id"], alert["id"], alert["id"], alert["id"]),
        ) or []
        items = [r for r in rows if not _is_scanner_family(str(r.get("alert_title") or ""))]
        return {"status": "present" if items else "empty", "items": items}
    except Exception as exc:  # noqa: BLE001
        logger.warning("incident sibling query unavailable: %s", type(exc).__name__)
        return {"status": "unavailable", "items": [], "note": type(exc).__name__}


def _tia_says_malicious(alert_id: str) -> bool:
    try:
        row = fetch_one(
            "SELECT disposition FROM tia_results WHERE alert_id = %s::uuid AND applied ORDER BY accepted_at DESC LIMIT 1;",
            (alert_id,),
        )
        return bool(row) and row.get("disposition") == "malicious"
    except Exception:  # noqa: BLE001  - results schema absent: nothing contradicts
        return False


def _enablement(tenant_id: str) -> Optional[Dict[str, Any]]:
    return fetch_one(
        "SELECT id::text AS id, playbook_version, enabled_by FROM tia_playbook_enablements "
        "WHERE tenant_id = %s::uuid AND playbook_id = %s AND disabled_at IS NULL;",
        (tenant_id, PLAYBOOK_ID),
    ) or None


def _hash(parts: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def decide(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Pure-ish decision from stored evidence. Returns outcome, reasons and the evidence it used."""
    reasons: List[str] = []
    if not _is_scanner_family(alert["alert_title"]):
        # Not this playbook's business: never create review work for alerts it does not cover.
        return {"outcome": "refuse", "reasons": ["rule_family_not_covered"], "evidence": {"alert": alert["id"], "title": alert["alert_title"]}}
    if not alert.get("source_ip") or not (alert.get("event_time") or alert.get("created_at")):
        return {"outcome": "review", "reasons": ["missing_evidence"], "evidence": {"alert": alert["id"]}}
    at = alert.get("event_time") or alert.get("created_at")
    auths = _authorizations(alert["tenant_id"], alert["source_ip"], at)
    in_scope = [a for a in auths if _auth_covers_destination(a, alert)]
    contra = _contradictions(alert)
    siblings = _incident_siblings(alert)
    evidence = {
        "alert": alert["id"], "title": alert["alert_title"], "severity": alert["severity"], "source_ip": alert["source_ip"],
        "host": alert["destination_host"], "dest_ip": alert.get("destination_ip"), "at": str(at),
        "authorizations": [a["id"] for a in auths], "in_scope": [a["id"] for a in in_scope],
        "contradictions": sorted(c["id"] for c in contra["items"]),
        "correlation_status": contra["status"],
        "incident_siblings": sorted(c["id"] for c in siblings["items"]),
        "incident_status": siblings["status"],
    }
    if contra["status"] == "unavailable":
        reasons.append("correlation_unavailable")  # we did not look; that is not "no malicious evidence"
    elif contra["items"]:
        reasons.append("contradicting_evidence")
    if siblings["status"] == "unavailable":
        reasons.append("incident_link_unavailable")
    elif siblings["items"]:
        reasons.append("incident_has_unresolved_malicious")
    if _tia_says_malicious(alert["id"]):
        reasons.append("investigation_marked_malicious")
        evidence["tia_malicious"] = True
    if reasons:
        return {"outcome": "review", "reasons": reasons, "evidence": evidence}
    if str(alert["severity"]).lower() == "critical":
        reasons.append("severity_not_eligible")
    if not _is_scanner_family(alert["alert_title"]):
        reasons.append("rule_family_not_covered")
    if not auths:
        reasons.append("source_not_authorized")
    elif not in_scope:
        reasons.append("outside_approved_scope")
    if reasons:
        return {"outcome": "refuse", "reasons": reasons, "evidence": evidence}
    return {"outcome": "close", "reasons": ["authorized_scanner_activity"], "evidence": evidence}


def evaluate(alert_id: str, tenant_id: str) -> Dict[str, Any]:
    """Evaluate and record. Raises LookupError for an alert outside the tenant (never reveals existence)."""
    alert = _load_alert(alert_id, tenant_id)
    if not alert:
        raise LookupError("alert not found for tenant")
    d = decide(alert)
    enablement = _enablement(tenant_id)
    live = bool(enablement and int(enablement["playbook_version"]) == PLAYBOOK_VERSION)
    mode = "enforced" if live else "shadow"
    ehash = _hash(d["evidence"])
    row = fetch_one(
        "INSERT INTO tia_playbook_evaluations (tenant_id, alert_id, playbook_id, playbook_version, outcome, mode, reasons, evidence_hash, disposition) "
        "VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s, %s) "
        "ON CONFLICT (alert_id, playbook_id, playbook_version, evidence_hash) DO UPDATE "
        "SET mode = EXCLUDED.mode, outcome = EXCLUDED.outcome, reasons = EXCLUDED.reasons, evaluated_at = now() "
        "WHERE tia_playbook_evaluations.executed_at IS NULL "
        "RETURNING id::text AS id, mode, outcome, executed_at, executed_verified;",
        (tenant_id, alert_id, PLAYBOOK_ID, PLAYBOOK_VERSION, d["outcome"], mode, json.dumps(d["reasons"]), ehash, DISPOSITION),
    ) or fetch_one(
        "SELECT id::text AS id, mode, outcome, executed_at, executed_verified FROM tia_playbook_evaluations "
        "WHERE alert_id = %s::uuid AND playbook_id = %s AND playbook_version = %s AND evidence_hash = %s;",
        (alert_id, PLAYBOOK_ID, PLAYBOOK_VERSION, ehash),
    )
    verdict = None
    if d["outcome"] == "close" and mode == "enforced":
        verdict = PlaybookVerdict(PLAYBOOK_ID, PLAYBOOK_VERSION, tenant_id, alert_id, row["id"], ehash, True, DISPOSITION, TARGET_STATUS)
    return {
        "evaluation_id": row["id"], "outcome": d["outcome"], "mode": mode, "reasons": d["reasons"], "evidence_hash": ehash,
        "executed": row["executed_at"] is not None, "verdict": verdict, "alert": alert, "would_close": d["outcome"] == "close",
    }


def _route_to_review(alert_id: str, tenant_id: str, reasons: List[str]) -> bool:
    """A contradicted or incomplete case goes to a human, durably. Never silently dropped."""
    try:
        from app.services import tia_acceptance as acc
        from app.services import tia_outbox

        binding = acc.open_attempt(alert_id=alert_id, tenant_id=tenant_id)
        acc.record_attempt_failure(
            attempt_id=binding["attempt_id"],
            category="playbook_conflict",
            error="verified playbook could not close: " + ",".join(reasons),
        )
        tia_outbox.kick()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("playbook review routing failed alert=%s: %s", alert_id, type(exc).__name__)
        return False


def execute_closure(alert_id: str, tenant_id: str) -> Dict[str, Any]:
    """Close one alert (authorized_benign) iff the playbook verdict, the policy and a fresh re-check agree."""
    ev = evaluate(alert_id, tenant_id)
    out: Dict[str, Any] = {"alert_id": alert_id, "outcome": ev["outcome"], "mode": ev["mode"], "reasons": ev["reasons"], "evaluation_id": ev["evaluation_id"]}
    if ev["outcome"] == "review":
        out["review_recorded"] = _route_to_review(alert_id, tenant_id, ev["reasons"])
    if ev["outcome"] != "close":
        return {**out, "executed": False, "why": ev["outcome"]}
    if ev["executed"]:
        return {**out, "executed": False, "why": "already_executed"}
    if ev["verdict"] is None:  # evaluated as eligible, but no live customer-authorised enablement: record only
        return {**out, "executed": False, "why": "playbook_not_enabled_shadow_only", "shadow": True}
    verdict = ev["verdict"]
    decision = authorize_ticket_action(
        {"type": "update_alert", "status": TARGET_STATUS},
        tenant_id=tenant_id, execution_source="verified_playbook", playbook_verdict=verdict, alert_id=alert_id,
    )
    if not decision.allow:
        return {**out, "executed": False, "why": decision.reason, "shadow": ev["mode"] == "shadow"}

    with db_transaction() as cur:
        cur.execute("SELECT status, ai_resolution_label FROM security_alerts WHERE id = %s::uuid AND tenant_id = %s::uuid FOR UPDATE;", (alert_id, tenant_id))
        row = cur.fetchone()
        if not row:
            return {**out, "executed": False, "why": "alert_missing"}
        status = str(row["status"])
        ours = status == TARGET_STATUS and row["ai_resolution_label"] == RESOLUTION_LABEL
        if status in TERMINAL and not ours:
            return {**out, "executed": False, "why": "already_terminal"}  # an analyst's decision is never overwritten
        if not ours:  # (resuming after a crash between the write and the evaluation record is a no-op write)
            cur.execute(
                "UPDATE security_alerts SET status = %s, ai_auto_closed = true, ai_resolution_label = %s, updated_at = now() "
                "WHERE id = %s::uuid AND tenant_id = %s::uuid AND status NOT IN ('closed','false_positive','resolved');",
                (TARGET_STATUS, RESOLUTION_LABEL, alert_id, tenant_id),
            )
        cur.execute("UPDATE tia_playbook_evaluations SET executed_at = now() WHERE id = %s::uuid AND executed_at IS NULL;", (ev["evaluation_id"],))
    after = fetch_one("SELECT status FROM security_alerts WHERE id = %s::uuid AND tenant_id = %s::uuid;", (alert_id, tenant_id)) or {}
    verified = after.get("status") == TARGET_STATUS
    fetch_one("UPDATE tia_playbook_evaluations SET executed_verified = %s WHERE id = %s::uuid RETURNING 1 AS x;", (verified, ev["evaluation_id"]))
    try:
        from app.services.audit_service import write_audit_event

        write_audit_event(
            action="alerts.playbook_close", entity_type="security_alert", entity_id=alert_id, tenant_id=tenant_id,
            actor_email=f"system:playbook:{PLAYBOOK_ID}@{PLAYBOOK_VERSION}", actor_role="system",
            details={"evaluation_id": ev["evaluation_id"], "evidence_hash": ev["evidence_hash"], "policy": decision.policy_version, "verified": verified, "disposition": decision.disposition},
        )
    except Exception:  # noqa: BLE001
        logger.exception("audit for playbook closure failed alert=%s", alert_id)
    return {**out, "executed": True, "verified": verified, "status_after": after.get("status")}


def reconcile(alert_id: str, tenant_id: str) -> Dict[str, Any]:
    """Re-check an alert this playbook closed. New contradicting evidence reopens it and routes it to a human."""
    closed = fetch_one(
        "SELECT id::text AS id FROM tia_playbook_evaluations WHERE alert_id = %s::uuid AND tenant_id = %s::uuid "
        "AND executed_at IS NOT NULL AND reopened_at IS NULL ORDER BY executed_at DESC LIMIT 1;",
        (alert_id, tenant_id),
    )
    alert = _load_alert(alert_id, tenant_id)
    if not closed or not alert:
        return {"reopened": False, "why": "not_closed_by_playbook"}
    d = decide({**alert, "status": "new"})
    if d["outcome"] == "close":
        return {"reopened": False, "why": "still_supported"}
    with db_transaction() as cur:
        cur.execute(
            "UPDATE security_alerts SET status = 'triaged', ai_auto_closed = false, updated_at = now() "
            "WHERE id = %s::uuid AND tenant_id = %s::uuid AND status = 'closed' AND ai_resolution_label = %s;",
            (alert_id, tenant_id, RESOLUTION_LABEL),
        )
        reopened = cur.rowcount == 1
        if reopened:
            cur.execute(
                "UPDATE tia_playbook_evaluations SET reopened_at = now(), reopen_reason = %s WHERE id = %s::uuid;",
                (",".join(d["reasons"]), closed["id"]),
            )
    if reopened:
        _route_to_review(alert_id, tenant_id, d["reasons"])
    return {"reopened": reopened, "reasons": d["reasons"]}


def shadow_report(tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """Measure the playbook against human review BEFORE enabling it. Only reviewed rows count."""
    params: List[Any] = [PLAYBOOK_ID, PLAYBOOK_VERSION]
    scope = ""
    if tenant_id:
        scope = " AND tenant_id = %s::uuid"
        params.append(tenant_id)
    rows = fetch_all(
        "SELECT outcome, reviewer_label, count(*)::int AS n FROM tia_playbook_evaluations "
        f"WHERE playbook_id = %s AND playbook_version = %s{scope} GROUP BY 1, 2;",
        tuple(params),
    ) or []
    total = sum(r["n"] for r in rows)
    reviewed = [r for r in rows if r["reviewer_label"]]
    would_close_reviewed = [r for r in reviewed if r["outcome"] == "close"]
    wrong = sum(r["n"] for r in would_close_reviewed if r["reviewer_label"] == "disagree")
    right = sum(r["n"] for r in would_close_reviewed if r["reviewer_label"] == "agree")
    return {
        "evaluations": total,
        "reviewed": sum(r["n"] for r in reviewed),
        "would_close_reviewed": right + wrong,
        "would_close_wrong": wrong,
        "would_close_agreement": (right / (right + wrong)) if (right + wrong) else None,
        "note": "Agreement is meaningful only on a reviewed set separate from the examples used to write the rules.",
        "enable_gate": "Enabling requires zero wrong closures on a reviewed set and a human recording customer authorisation.",
    }


def run_for_alert(alert_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """Pipeline hook, called after an investigation is handled. Never raises into the queue.

    Only scanner-family, non-critical alerts are evaluated. With no customer-authorised enablement the
    evaluation is recorded as shadow and nothing is written to the alert.
    """
    try:
        if not schema_ready():
            return None
        alert = _load_alert(alert_id, tenant_id)
        if not alert or alert["status"] in TERMINAL:
            return None
        if not _is_scanner_family(alert["alert_title"]) or str(alert["severity"]).lower() == "critical":
            return None
        return execute_closure(alert_id, tenant_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("playbook hook failed alert=%s: %s", alert_id, type(exc).__name__)
        return None
