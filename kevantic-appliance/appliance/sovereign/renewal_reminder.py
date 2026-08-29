"""Sovereign Edge offline license renewal reminders (on-appliance, customer-visible)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_WARN_DAYS = (90, 30, 14, 7, 1, 0)
REMINDER_FILENAME = "renewal-reminder.json"


def _state_root() -> Path:
    import os

    for env_name in ("KEVANTIC_STATE_DIR", "NIKTIAR_STATE_DIR", "JUNEXIS_STATE_DIR"):
        env = os.environ.get(env_name, "").strip()
        if env:
            return Path(env)
    for default in (Path("/var/lib/niktiar"), Path("/var/lib/junexis"), Path("/var/lib/kevantic")):
        if default.is_dir():
            return default
    return Path("/var/lib/kevantic")


def reminder_path() -> Path:
    return _state_root() / REMINDER_FILENAME


def _days_until(exp: int, *, now: Optional[int] = None) -> int:
    current = int(now or time.time())
    return int((int(exp) - current) // 86400)


def build_renewal_reminder(
    *,
    exp: Optional[int],
    tenant_id: Optional[str] = None,
    jti: Optional[str] = None,
    warn_days: tuple[int, ...] = DEFAULT_WARN_DAYS,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    """Build customer-safe renewal reminder payload (no license apply path)."""
    current = int(now or time.time())
    if not exp:
        return {
            "active": False,
            "level": "none",
            "message": None,
            "action": None,
            "checked_at": current,
        }

    days_left = _days_until(int(exp), now=current)
    level = "none"
    if days_left < 0:
        level = "expired"
    elif days_left == 0:
        level = "critical"
    else:
        for threshold in sorted(warn_days, reverse=True):
            if days_left <= threshold:
                level = "warning" if days_left > 7 else "urgent"
                break

    active = level in ("warning", "urgent", "critical", "expired")
    if level == "expired":
        message = (
            "Your NikTiar Sovereign Edge license has expired. "
            "Contact your MSSP account team to request a renewal license."
        )
    elif active:
        message = (
            f"Your NikTiar Sovereign Edge license expires in {max(days_left, 0)} day(s). "
            "Contact your MSSP account team to arrange offline renewal delivery."
        )
    else:
        message = None

    return {
        "active": active,
        "level": level,
        "days_until_expiry": days_left,
        "exp": int(exp),
        "tenant_id": tenant_id,
        "jti": jti,
        "message": message,
        "action": "contact_mssp_for_offline_renewal" if active else None,
        "customer_may_apply_license": False,
        "checked_at": current,
    }


def write_renewal_reminder(payload: Dict[str, Any]) -> Path:
    path = reminder_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    # Mirror to sibling state dirs for junexis/kevantic dual-layout appliances.
    for sibling in (Path("/var/lib/junexis"), Path("/var/lib/kevantic"), Path("/var/lib/niktiar")):
        if sibling == path.parent or not sibling.is_dir():
            continue
        alt = sibling / REMINDER_FILENAME
        try:
            alt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except OSError:
            pass
    return path


def load_renewal_reminder() -> Dict[str, Any]:
    path = reminder_path()
    if not path.is_file():
        return build_renewal_reminder(exp=None)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else build_renewal_reminder(exp=None)
    except json.JSONDecodeError:
        return build_renewal_reminder(exp=None)


def refresh_renewal_reminder_from_entitlements(ents: Dict[str, Any]) -> Dict[str, Any]:
    payload = build_renewal_reminder(
        exp=ents.get("exp"),
        tenant_id=ents.get("tenant_id"),
        jti=ents.get("jti"),
    )
    write_renewal_reminder(payload)
    return payload
