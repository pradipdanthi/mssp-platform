"""Scheduled SOC routines for Tia (morning brief, etc.)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from app.db.session import redis_client
from app.services.soc_console_activity import push_local_activity
from app.services.soc_console_operator import render_wake_briefing

logger = logging.getLogger(__name__)

_KEY = "mssp:tia:routines"
_DEFAULT_TZ = "Asia/Kolkata"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _defaults() -> List[Dict[str, Any]]:
    return [
        {
            "id": "morning_soc_brief",
            "name": "Morning SOC brief",
            "description": "Proactive welcome-style briefing: alerts, urgency, stack health.",
            "enabled": True,
            "hour_local": 9,
            "minute_local": 0,
            "timezone": _DEFAULT_TZ,
            "last_run_at": None,
            "last_run_date_local": None,
            "last_spoken": None,
            "kind": "wake_briefing",
        },
        {
            "id": "afternoon_check",
            "name": "Afternoon stack check",
            "description": "Mid-day urgency + engine reachability sweep.",
            "enabled": False,
            "hour_local": 15,
            "minute_local": 0,
            "timezone": _DEFAULT_TZ,
            "last_run_at": None,
            "last_run_date_local": None,
            "last_spoken": None,
            "kind": "wake_briefing",
        },
    ]


def _load() -> List[Dict[str, Any]]:
    try:
        r = redis_client()
        raw = r.get(_KEY)
        if not raw:
            items = _defaults()
            _save(items)
            return items
        data = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
        if not isinstance(data, list) or not data:
            items = _defaults()
            _save(items)
            return items
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("routines load failed: %s", exc)
        return _defaults()


def _save(items: List[Dict[str, Any]]) -> None:
    try:
        r = redis_client()
        r.set(_KEY, json.dumps(items), ex=60 * 60 * 24 * 90)
    except Exception as exc:  # noqa: BLE001
        logger.warning("routines save failed: %s", exc)


def list_routines() -> List[Dict[str, Any]]:
    return _load()


def update_routine(routine_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    items = _load()
    for item in items:
        if item.get("id") != routine_id:
            continue
        if "enabled" in patch:
            item["enabled"] = bool(patch["enabled"])
        if "hour_local" in patch:
            item["hour_local"] = max(0, min(23, int(patch["hour_local"])))
        if "minute_local" in patch:
            item["minute_local"] = max(0, min(59, int(patch["minute_local"])))
        if "timezone" in patch and str(patch["timezone"]).strip():
            item["timezone"] = str(patch["timezone"]).strip()[:64]
        _save(items)
        return item
    raise KeyError("routine_not_found")


def run_routine(routine_id: str, *, force: bool = False) -> Dict[str, Any]:
    items = _load()
    found: Optional[Dict[str, Any]] = None
    for item in items:
        if item.get("id") == routine_id:
            found = item
            break
    if not found:
        raise KeyError("routine_not_found")
    if not found.get("enabled") and not force:
        raise ValueError("routine_disabled")

    brief = render_wake_briefing()
    tz_name = str(found.get("timezone") or _DEFAULT_TZ)
    try:
        local_now = datetime.now(ZoneInfo(tz_name))
    except Exception:  # noqa: BLE001
        local_now = datetime.now(timezone.utc)
        tz_name = "UTC"

    found["last_run_at"] = _utc()
    found["last_run_date_local"] = local_now.date().isoformat()
    found["last_spoken"] = brief.get("spoken_answer")
    found["last_answer"] = brief.get("answer")
    found["last_priority"] = (brief.get("snapshot") or {}).get("priority")
    _save(items)

    push_local_activity(
        kind="routine",
        title=f"Tia routine · {found.get('name')}",
        detail=str(brief.get("spoken_answer") or "")[:240],
        severity="info" if (found.get("last_priority") == "clear") else "high",
        actor="Tia",
    )
    return {
        "routine": found,
        "briefing": {
            "spoken_answer": brief.get("spoken_answer"),
            "answer": brief.get("answer"),
            "priority": found.get("last_priority"),
        },
    }


def due_routines(*, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Return enabled routines that should fire once today at/after their local time."""
    due: List[Dict[str, Any]] = []
    for item in _load():
        if not item.get("enabled"):
            continue
        tz_name = str(item.get("timezone") or _DEFAULT_TZ)
        try:
            local_now = now.astimezone(ZoneInfo(tz_name)) if now else datetime.now(ZoneInfo(tz_name))
        except Exception:  # noqa: BLE001
            local_now = now or datetime.now(timezone.utc)
        target_h = int(item.get("hour_local") or 9)
        target_m = int(item.get("minute_local") or 0)
        if (local_now.hour, local_now.minute) < (target_h, target_m):
            continue
        if item.get("last_run_date_local") == local_now.date().isoformat():
            continue
        due.append(item)
    return due


def tick_routines() -> List[Dict[str, Any]]:
    """Run any due routines (idempotent per local day)."""
    ran: List[Dict[str, Any]] = []
    for item in due_routines():
        try:
            ran.append(run_routine(str(item["id"]), force=True))
        except Exception as exc:  # noqa: BLE001
            logger.warning("routine %s failed: %s", item.get("id"), exc)
    return ran
