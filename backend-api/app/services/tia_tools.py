"""TIA typed tool layer, shared by chat and voice.

Every operation TIA can perform for an operator is declared here and nowhere else. The
registry lists only operations that are really implemented, so a capability question is
answered from code, not from a prompt. Every call goes through ``authorize`` (role) and
every query is filtered by the conversation's tenant scope on the SERVER: the model, the
browser and the operator's words never choose the tenant filter.

Effect classes
  read        queries data, changes nothing
  ui          asks the operator's dashboard to navigate (verified by acknowledgement)
  write       changes platform data                  (none implemented here)
  disruptive  isolates, disables, blocks, contains   (never executed here; approval workflow)

Alert text, hostnames and descriptions are returned as DATA. Nothing in this module treats
them as instructions.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.db.session import fetch_all, fetch_one

logger = logging.getLogger(__name__)

SOC_ROLES: Tuple[str, ...] = ("platform_admin", "soc_manager", "soc_analyst")
OPEN_STATUS_SQL = "status NOT IN ('closed','false_positive')"
SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")


class ToolError(Exception):
    """A tool refused or could not run. ``code`` is safe to show the operator."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Scope:
    """Who is asking, from where, and which tenant the conversation is bound to."""

    operator_email: str
    operator_id: Optional[str]
    role: str
    session_id: str
    tenant_id: Optional[str] = None  # None = platform scope (all tenants, SOC roles only)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    effect: str  # read | ui | write | disruptive
    roles: Tuple[str, ...]
    summary: str
    needs_target: bool = False


REGISTRY: Dict[str, ToolSpec] = {
    t.name: t
    for t in (
        ToolSpec("count_alerts", "read", SOC_ROLES, "Open alert counts by severity, in the current scope."),
        ToolSpec("list_alerts", "read", SOC_ROLES, "List the most urgent open alerts, in the current scope."),
        ToolSpec("describe_alert", "read", SOC_ROLES, "Summarise one alert and its investigation state.", True),
        ToolSpec("explain_evidence", "read", SOC_ROLES, "State what the stored record shows and what it lacks.", True),
        ToolSpec("next_alert", "read", SOC_ROLES, "The next alert after the selected one in the last listing."),
        ToolSpec("engine_health", "read", SOC_ROLES, "Layered engine health (reachability, API, login, application, telemetry freshness). Hosts and error detail need manager or admin."),
        ToolSpec("research_lookup", "read", SOC_ROLES, "Cited lookup of a PUBLIC identifier (CVE, MITRE technique) from approved reference sites. Off unless configured."),
        ToolSpec("open_case", "ui", SOC_ROLES, "Open an alert on the operator's screen (verified by acknowledgement).", True),
        ToolSpec("start_investigation", "async", SOC_ROLES, "Queue a durable deep investigation and return immediately with the job id. Does not wait for the model.", True),
        ToolSpec("investigation_status", "read", SOC_ROLES, "The queued or running investigation for an alert, without waiting for it.", True),
        ToolSpec("platform_inventory", "read", SOC_ROLES, "Documented MSSP components plus live hypervisor status where reachable."),
        ToolSpec("component_lookup", "read", SOC_ROLES, "Which VM runs a component, what depends on it, and live health if an adapter exists.", True),
        ToolSpec("ingest_status", "read", SOC_ROLES, "Separate reachability, authentication, processing and event ingest freshness for an engine."),
        ToolSpec("customers_overview", "read", SOC_ROLES, "Customers in the current conversation scope with live open-alert counts."),
        ToolSpec("portal_status", "read", SOC_ROLES, "Admin, customer and SOC UI reachability — not a claim that engines are healthy."),
        ToolSpec("assess_criticality", "read", SOC_ROLES, "Why an alert is labelled critical, without treating the label as a confirmed incident.", True),
        ToolSpec("investigation_delay", "read", SOC_ROLES, "Why a deep investigation may be delayed (queue, worker, agent, review).", True),
        ToolSpec("known_unknowns", "read", SOC_ROLES, "What the record and investigation actually show versus what remains unverified.", True),
    )
}

# Operations deliberately NOT implemented as tools. Asking for one returns an honest
# refusal naming the supported path. The registry never lists them as capabilities.
NOT_AVAILABLE_BY_CHAT = (
    "isolate a host", "disable an account", "block an address", "quarantine a file", "kill a process",
    "close or resolve an alert", "send a customer notification",
)


def capabilities() -> List[Dict[str, Any]]:
    return [
        {"name": s.name, "effect": s.effect, "summary": s.summary, "requires_target": s.needs_target}
        for s in REGISTRY.values()
    ]


def authorize(tool: str, scope: Scope) -> ToolSpec:
    spec = REGISTRY.get(tool)
    if spec is None:
        raise ToolError("unknown_tool", f"{tool} is not a TIA capability")
    if scope.role not in spec.roles:
        raise ToolError("forbidden", "Your role cannot use this tool")
    if spec.effect in ("write", "disruptive"):  # defence in depth: nothing here may reach these
        raise ToolError("approval_required", "This needs human approval in Needs You")
    return spec


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def valid_uuid(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not _UUID_RE.match(text):
        return None
    return str(uuid.UUID(text))


def resolve_tenant(tenant_id: Optional[str], short_code: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return {id,name,short_code} for an existing tenant, or None. Never trusts the caller."""
    if tenant_id:
        tid = valid_uuid(tenant_id)
        if not tid:
            return None
        row = fetch_one("SELECT id::text AS id, name, short_code FROM tenants WHERE id = %s::uuid;", (tid,))
        return row or None
    if short_code:
        row = fetch_one(
            "SELECT id::text AS id, name, short_code FROM tenants WHERE lower(short_code) = lower(%s);",
            (short_code.strip(),),
        )
        return row or None
    return None


def _scoped_clause(scope: Scope, column: str = "tenant_id") -> Tuple[str, Tuple[Any, ...]]:
    if scope.tenant_id:
        return f" AND {column} = %s::uuid", (scope.tenant_id,)
    return "", ()


# --------------------------------------------------------------------------
# read tools
# --------------------------------------------------------------------------


def count_alerts(scope: Scope) -> Dict[str, Any]:
    authorize("count_alerts", scope)
    clause, params = _scoped_clause(scope)
    rows = fetch_all(
        f"SELECT lower(severity) AS sev, count(*)::int AS n FROM security_alerts WHERE {OPEN_STATUS_SQL}{clause} GROUP BY 1;",
        params,
    )
    by_sev = {str(r["sev"]): int(r["n"]) for r in rows}
    ordered = {s: by_sev.get(s, 0) for s in SEVERITY_ORDER}
    for k, v in by_sev.items():  # severities outside the standard set stay visible
        ordered.setdefault(k, v)
    return {
        "scope": "tenant" if scope.tenant_id else "platform",
        "open_total": sum(by_sev.values()),
        "by_severity": ordered,
        "critical": ordered["critical"],
        "high": ordered["high"],
    }


def list_alerts(scope: Scope, *, severities: Tuple[str, ...] = ("critical", "high"), limit: int = 5) -> List[Dict[str, Any]]:
    authorize("list_alerts", scope)
    limit = max(1, min(int(limit), 10))
    clause, params = _scoped_clause(scope, "sa.tenant_id")
    rows = fetch_all(
        f"""
        SELECT sa.id::text AS id, sa.alert_title AS title, lower(sa.severity) AS severity, sa.status,
               sa.destination_host AS host, sa.source_tool, t.short_code, t.name AS tenant_name,
               (sa.event_time AT TIME ZONE 'utc')::text AS event_time,
               sa.occurrence_count, (sa.first_seen_at AT TIME ZONE 'utc')::text AS first_seen_at,
               (sa.last_seen_at AT TIME ZONE 'utc')::text AS last_seen_at
        FROM security_alerts sa JOIN tenants t ON t.id = sa.tenant_id
        WHERE sa.{OPEN_STATUS_SQL} AND lower(sa.severity) = ANY(%s){clause}
        ORDER BY array_position(%s::text[], lower(sa.severity)), sa.created_at DESC
        LIMIT %s;
        """,
        (list(severities), *params, list(SEVERITY_ORDER), limit),
    )
    return list(rows)


def get_alert_row(scope: Scope, alert_id: Any) -> Optional[Dict[str, Any]]:
    """The alert, only if it exists AND is inside the scope. Otherwise None (never 'forbidden',
    so the caller cannot learn that an id exists in another tenant)."""
    aid = valid_uuid(alert_id)
    if not aid:
        return None
    clause, params = _scoped_clause(scope, "sa.tenant_id")
    row = fetch_one(
        f"""
        SELECT sa.id::text AS id, sa.tenant_id::text AS tenant_id, sa.alert_title AS title,
               lower(sa.severity) AS severity, sa.status, sa.source_tool, sa.alert_description AS description,
               sa.destination_host AS host, sa.source_user AS user_name, sa.source_ip::text AS source_ip,
               sa.destination_ip::text AS destination_ip, sa.parent_process, sa.parent_command_line,
               sa.current_directory, sa.integrity_level, sa.hash_sha256, sa.process_id,
               sa.ai_verdict, sa.ai_confidence::float AS ai_confidence, sa.ai_queue, sa.ai_triage_status,
               sa.ai_likely_attack_type, sa.ai_technical_summary,
               (sa.event_time AT TIME ZONE 'utc')::text AS event_time,
               sa.occurrence_count, (sa.first_seen_at AT TIME ZONE 'utc')::text AS first_seen_at,
               (sa.last_seen_at AT TIME ZONE 'utc')::text AS last_seen_at,
               t.short_code, t.name AS tenant_name
        FROM security_alerts sa JOIN tenants t ON t.id = sa.tenant_id
        WHERE sa.id = %s::uuid{clause};
        """,
        (aid, *params),
    )
    return row or None


def _investigation_state(alert_id: str) -> Dict[str, Any]:
    """Review item and latest accepted result. Missing migrations are reported, not hidden."""
    try:
        item = fetch_one(
            """
            SELECT reason_code, status, assessed_priority, notify_urgency, assigned_to,
                   (due_at AT TIME ZONE 'utc')::text AS due_at, analysis_available, highest_finding
            FROM tia_review_items WHERE alert_id = %s::uuid AND status <> 'resolved';
            """,
            (alert_id,),
        )
        result = fetch_one(
            """
            SELECT execution_status, error_category, verdict, confidence::float AS confidence, disposition,
                   applied, apply_reason, (accepted_at AT TIME ZONE 'utc')::text AS accepted_at
            FROM tia_results WHERE alert_id = %s::uuid ORDER BY accepted_at DESC LIMIT 1;
            """,
            (alert_id,),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("investigation state unavailable: %s", type(exc).__name__)
        return {"available": False, "reason": "investigation tables unavailable"}
    checked = None
    model_view = None
    try:
        att = fetch_one(
            "SELECT a.evidence_manifest, r.outcome -> 'llm' ->> 'summary' AS summary, r.outcome -> 'llm' ->> 'root_cause' AS root_cause "
            "FROM tia_investigation_attempts a LEFT JOIN tia_results r ON r.attempt_id = a.id "
            "WHERE a.alert_id = %s::uuid ORDER BY a.dispatched_at DESC LIMIT 1;",
            (alert_id,),
        )
        manifest = (att or {}).get("evidence_manifest") or {}
        if manifest.get("sections"):
            checked = {
                "sent_form": manifest.get("sent_form"),
                "sections": {n: {"status": s.get("status"), "items": s.get("items"), "note": s.get("note"), "missing": s.get("missing") or []} for n, s in manifest["sections"].items()},
            }
        if att and att.get("summary"):
            model_view = {"summary": att["summary"][:600], "root_cause": (att.get("root_cause") or "")[:300] or None}
    except Exception as exc:  # noqa: BLE001  - pre-122 schema: no manifest column
        logger.info("evidence manifest unavailable: %s", type(exc).__name__)
    return {"available": True, "review_item": item or None, "latest_result": result or None, "checked": checked, "model_view": model_view}


def describe_alert(scope: Scope, alert_id: Any) -> Dict[str, Any]:
    authorize("describe_alert", scope)
    row = get_alert_row(scope, alert_id)
    if not row:
        raise ToolError("not_found", "I can't find that alert in this scope.")
    return {"alert": row, "investigation": _investigation_state(row["id"])}


_EVIDENCE_FIELDS = (
    ("host", "affected host"),
    ("user_name", "user"),
    ("source_ip", "source address"),
    ("destination_ip", "destination address"),
    ("parent_process", "parent process"),
    ("parent_command_line", "parent command line"),
    ("current_directory", "working directory"),
    ("integrity_level", "integrity level"),
    ("hash_sha256", "file hash"),
    ("process_id", "process id"),
)


def explain_evidence(scope: Scope, alert_id: Any) -> Dict[str, Any]:
    """What the stored record shows, what it lacks, and the state of any investigation.

    This does not diagnose. It never states a cause that the record does not contain.
    """
    authorize("explain_evidence", scope)
    row = get_alert_row(scope, alert_id)
    if not row:
        raise ToolError("not_found", "I can't find that alert in this scope.")
    present = [{"field": label, "value": str(row[key])[:200]} for key, label in _EVIDENCE_FIELDS if row.get(key)]
    missing = [label for key, label in _EVIDENCE_FIELDS if not row.get(key)]
    return {
        "alert": {k: row[k] for k in ("id", "title", "severity", "status", "source_tool", "event_time", "short_code", "tenant_name")},
        "description": (row.get("description") or "")[:500],
        "present": present,
        "missing": missing,
        "prior_ai_assessment": {
            "verdict": row.get("ai_verdict"),
            "confidence": row.get("ai_confidence"),
            "attack_type": row.get("ai_likely_attack_type"),
            "queue": row.get("ai_queue"),
        },
        "investigation": _investigation_state(row["id"]),
    }


def next_alert(scope: Scope, referenced_ids: List[str], selected_id: Optional[str]) -> Optional[str]:
    """The alert after the selected one in the last listing, still inside scope."""
    authorize("next_alert", scope)
    ids = [i for i in referenced_ids if valid_uuid(i)]
    if not ids:
        return None
    start = ids.index(selected_id) + 1 if selected_id in ids else 0
    for candidate in ids[start:]:
        if get_alert_row(scope, candidate):
            return candidate
    return None


def open_case_target(scope: Scope, alert_id: Any) -> Dict[str, Any]:
    """Validate a navigation target. The command itself is created by the conversation layer."""
    authorize("open_case", scope)
    row = get_alert_row(scope, alert_id)
    if not row:
        raise ToolError("not_found", "I can't find that alert in this scope.")
    return {
        "alert_id": row["id"],
        "title": row["title"],
        "severity": row["severity"],
        "tenant_id": row["tenant_id"],
        "short_code": row["short_code"],
        "path": f"/alerts/{row['id']}",
    }


def engine_health(scope: Scope, *, engine: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """Live layered health. Platform-wide infrastructure, so detail is role-gated (see redact_for_role)."""
    authorize("engine_health", scope)
    from app.services import tia_engine_health as eh

    report = eh.get_health(force=force, only=engine)
    return eh.redact_for_role(report, scope.role)


def start_investigation(scope: Scope, alert_id: Any) -> Dict[str, Any]:
    """Enqueue a durable job. Returns the job id; never blocks on Cursor or the model."""
    authorize("start_investigation", scope)
    row = get_alert_row(scope, alert_id)
    if not row:
        raise ToolError("not_found", "I can't find that alert in this scope.")
    from app.services import tia_jobs

    out = tia_jobs.enqueue(alert_id=row["id"], tenant_id=row["tenant_id"], severity=row["severity"], source="operator")
    if not out.get("job_id"):
        raise ToolError("enqueue_failed", "I couldn't queue the investigation.")
    from app.services.ai_alert_queue import _ensure_worker

    _ensure_worker()
    return {
        "alert_id": row["id"],
        "title": row["title"],
        "short_code": row["short_code"],
        "job_id": out["job_id"],
        "created": bool(out["created"]),
        "state": "queued" if out["created"] else "already_queued",
    }


def investigation_status(scope: Scope, alert_id: Any) -> Dict[str, Any]:
    authorize("investigation_status", scope)
    row = get_alert_row(scope, alert_id)
    if not row:
        raise ToolError("not_found", "I can't find that alert in this scope.")
    from app.services import tia_jobs

    return {"alert_id": row["id"], "job": tia_jobs.latest_for_alert(row["id"]), "investigation": _investigation_state(row["id"])}


def research_behaviour(scope: Scope, alert_id: Any) -> Dict[str, Any]:
    """Sanitised public-binary lookup. Customer names, hosts, users and command bodies never leave."""
    authorize("research_lookup", scope)
    row = get_alert_row(scope, alert_id)
    if not row:
        raise ToolError("not_found", "I can't find that alert in this scope.")
    from app.services import tia_research_policy as rp

    try:
        return rp.behavioural_lookup(
            tenant_id=row["tenant_id"],
            alert=row,
            provider="lolbas",
            requested_by=scope.operator_email,
        )
    except rp.Refused as refused:
        raise ToolError(refused.code, f"Behavioural research refused: {refused.code.replace('_', ' ')}") from refused


def platform_inventory(scope: Scope) -> Dict[str, Any]:
    authorize("platform_inventory", scope)
    from app.services import tia_knowledge as kn

    return kn.platform_inventory(scope)


def component_lookup(scope: Scope, component_id: str) -> Dict[str, Any]:
    authorize("component_lookup", scope)
    from app.services import tia_knowledge as kn

    return kn.component_lookup(scope, component_id)


def ingest_status(scope: Scope, engine_id: str = "wazuh") -> Dict[str, Any]:
    authorize("ingest_status", scope)
    from app.services import tia_knowledge as kn

    return kn.ingest_status(scope, engine_id)


def customers_overview(scope: Scope) -> Dict[str, Any]:
    authorize("customers_overview", scope)
    from app.services import tia_knowledge as kn

    return kn.customers_overview(scope)


def portal_status(scope: Scope) -> Dict[str, Any]:
    authorize("portal_status", scope)
    from app.services import tia_knowledge as kn

    return kn.portal_status(scope)


def assess_criticality(scope: Scope, alert_id: Any) -> Dict[str, Any]:
    authorize("assess_criticality", scope)
    from app.services import tia_knowledge as kn

    return kn.assess_criticality(scope, str(alert_id))


def investigation_delay(scope: Scope, alert_id: Any) -> Dict[str, Any]:
    authorize("investigation_delay", scope)
    from app.services import tia_knowledge as kn

    return kn.investigation_delay(scope, str(alert_id))


def known_unknowns(scope: Scope, alert_id: Any) -> Dict[str, Any]:
    authorize("known_unknowns", scope)
    from app.services import tia_knowledge as kn

    return kn.known_unknowns(scope, str(alert_id))


def research_lookup(scope: Scope, *, kind: str, value: str) -> Dict[str, Any]:
    """Public reference lookup. Only (kind, value) of a public identifier is ever sent out."""
    authorize("research_lookup", scope)
    from app.services import tia_research as r
    from app.services import tia_research_policy as rp

    if kind == "sha256" and not rp.granted(scope.tenant_id, "virustotal", "hash_reputation"):
        # A hash comes from a customer's telemetry: the platform allow-list is not the customer's consent.
        raise ToolError("tenant_not_authorised", "This customer has not authorised hash lookups")
    try:
        return r.lookup(kind, value)
    except r.ResearchRefused as refused:
        raise ToolError(refused.code, f"Research lookup refused: {refused.code.replace('_', ' ')}") from refused
    except Exception as exc:  # noqa: BLE001
        raise ToolError("research_unavailable", "The reference site did not answer.") from exc
