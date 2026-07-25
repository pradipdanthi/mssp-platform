"""KB-067: Customer-safe monthly report snapshot shape (stored in metrics JSONB)."""

from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1

EMPTY_NARRATIVE = {
    "period_highlights": "",
    "trends": "",
    "next_month_focus": "",
    "leadership_asks": "",
}


def empty_snapshot() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": None,
        "period": {},
        "cover": {},
        "posture": {},
        "detection": {},
        "incidents": {},
        "recommendations": {},
        "notifications": {},
        "narrative": dict(EMPTY_NARRATIVE),
        "deferred_kpis_note": (
            "MTTD, MTTR, and timed SLA compliance will appear in a future release "
            "once first-response timers are instrumented in the control plane."
        ),
    }


def merge_narrative(
    snapshot: Dict[str, Any],
    narrative: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Preserve SOC narrative fields when refreshing auto-calculated sections."""
    out = dict(snapshot)
    current = dict(EMPTY_NARRATIVE)
    existing = snapshot.get("narrative") if isinstance(snapshot.get("narrative"), dict) else {}
    current.update({k: (existing.get(k) or "") for k in EMPTY_NARRATIVE})
    if narrative:
        for key in EMPTY_NARRATIVE:
            if key in narrative and narrative[key] is not None:
                current[key] = str(narrative[key])
    out["narrative"] = current
    return out


def project_customer_safe(snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Return only the approved customer-facing projection.
    Never includes IPs, raw alerts, internal notes, or file paths.
    """
    base = empty_snapshot()
    if not isinstance(snapshot, dict):
        return base

    def copy_block(name: str) -> Dict[str, Any]:
        block = snapshot.get(name)
        return dict(block) if isinstance(block, dict) else {}

    # Notable incidents: only allow known safe keys
    incidents = copy_block("incidents")
    notable_in = incidents.get("notable") if isinstance(incidents.get("notable"), list) else []
    notable_out: List[Dict[str, Any]] = []
    for item in notable_in[:25]:
        if not isinstance(item, dict):
            continue
        notable_out.append(
            {
                "incident_number": item.get("incident_number"),
                "title": item.get("title"),
                "severity": item.get("severity"),
                "status": item.get("status"),
                "customer_visible_summary": item.get("customer_visible_summary"),
            }
        )
    incidents["notable"] = notable_out

    recs = copy_block("recommendations")
    items_in = recs.get("items") if isinstance(recs.get("items"), list) else []
    items_out: List[Dict[str, Any]] = []
    for item in items_in[:50]:
        if not isinstance(item, dict):
            continue
        items_out.append(
            {
                "title": item.get("title"),
                "priority": item.get("priority"),
                "status": item.get("status"),
                "category": item.get("category"),
                "due_at": item.get("due_at"),
            }
        )
    recs["items"] = items_out

    narrative = copy_block("narrative")
    for key in EMPTY_NARRATIVE:
        narrative.setdefault(key, "")

    return {
        "schema_version": snapshot.get("schema_version", SCHEMA_VERSION),
        "generated_at": snapshot.get("generated_at"),
        "period": copy_block("period"),
        "cover": copy_block("cover"),
        "posture": copy_block("posture"),
        "detection": copy_block("detection"),
        "incidents": incidents,
        "recommendations": recs,
        "notifications": copy_block("notifications"),
        "narrative": narrative,
        "deferred_kpis_note": snapshot.get("deferred_kpis_note")
        or base["deferred_kpis_note"],
    }
