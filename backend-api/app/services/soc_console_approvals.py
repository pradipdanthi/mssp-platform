"""Pending approval queue for Tia ticket actions (Jarvis-style Needs You)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.session import redis_client
from app.services.soc_console_tia import apply_tia_actions

logger = logging.getLogger(__name__)

_KEY = "mssp:tia:pending_approvals"
_MAX = 40


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> List[Dict[str, Any]]:
    try:
        r = redis_client()
        raw = r.get(_KEY)
        if not raw:
            return []
        data = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
        return data if isinstance(data, list) else []
    except Exception as exc:  # noqa: BLE001
        logger.warning("approvals load failed: %s", exc)
        return []


def _save(items: List[Dict[str, Any]]) -> None:
    try:
        r = redis_client()
        r.set(_KEY, json.dumps(items[:_MAX]), ex=60 * 60 * 24 * 14)
    except Exception as exc:  # noqa: BLE001
        logger.warning("approvals save failed: %s", exc)


def enqueue_approval(
    *,
    actions: List[Dict[str, Any]],
    question: str,
    answer_excerpt: str,
    actor_email: str,
    policy_version: Optional[str] = None,
    policy_decisions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Stage proposed Tia actions for operator Approve / Decline."""
    clean_actions = [a for a in (actions or []) if isinstance(a, dict)][:5]
    if not clean_actions:
        raise ValueError("no_actions")
    item = {
        "id": str(uuid.uuid4()),
        "created_at": _utc(),
        "status": "pending",
        "actor_email": actor_email,
        "question": (question or "")[:500],
        "answer_excerpt": (answer_excerpt or "")[:400],
        "actions": clean_actions,
        "summary": _summarize(clean_actions),
        "policy_version": policy_version,
        "policy_decisions": list(policy_decisions or []),
    }
    items = [item] + [i for i in _load() if i.get("status") == "pending"]
    _save(items[:_MAX])
    return item


def list_approvals(*, status: str = "pending", limit: int = 20) -> List[Dict[str, Any]]:
    want = (status or "pending").lower()
    items = _load()
    if want != "all":
        items = [i for i in items if str(i.get("status") or "").lower() == want]
    return items[: max(1, min(int(limit or 20), 50))]


def get_approval(approval_id: str) -> Optional[Dict[str, Any]]:
    aid = (approval_id or "").strip()
    for item in _load():
        if item.get("id") == aid:
            return item
    return None


def decide_approval(
    approval_id: str,
    *,
    decision: str,
    actor_user_id: Optional[str],
    actor_email: str,
) -> Dict[str, Any]:
    decision_v = (decision or "").strip().lower()
    if decision_v not in ("approve", "decline"):
        raise ValueError("decision must be approve or decline")

    items = _load()
    found: Optional[Dict[str, Any]] = None
    for item in items:
        if item.get("id") == approval_id:
            found = item
            break
    if not found:
        raise KeyError("approval_not_found")
    if found.get("status") != "pending":
        raise ValueError("approval_not_pending")

    results: List[Dict[str, Any]] = []
    if decision_v == "approve":
        results = apply_tia_actions(
            list(found.get("actions") or []),
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            execution_source="analyst_approval",
        )
        found["status"] = "approved"
        found["results"] = results
    else:
        found["status"] = "declined"
        found["results"] = []

    found["decided_at"] = _utc()
    found["decided_by"] = actor_email
    _save(items)
    return found


def _summarize(actions: List[Dict[str, Any]]) -> str:
    bits = []
    for a in actions:
        t = str(a.get("type") or "action")
        if t == "update_alert":
            bits.append(f"alert→{a.get('status')}")
        elif t == "update_incident":
            bits.append(f"incident→{a.get('status')}")
        elif t == "comment_incident":
            bits.append("incident comment")
        else:
            bits.append(t)
    return ", ".join(bits)[:180]


def pending_count() -> int:
    return len(list_approvals(status="pending", limit=_MAX))
