"""Customer privacy scrubbing before any cloud forward."""

from __future__ import annotations

import copy
import re
from typing import Any

# Keys (case-insensitive) stripped or redacted from nested dicts
SENSITIVE_KEYS = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "set-cookie",
    "private_key",
    "raw_event",
    "raw_json",
    "email_body",
    "mail_body",
    "message_body",
    "full_log",
    "full_message",
    "pcap",
    "packet",
}

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# crude password-assignment scrub in free text
PASS_ASSIGN_RE = re.compile(
    r"(?i)\b(password|passwd|pwd)\s*[:=]\s*\S+"
)


def _scrub_string(value: str) -> str:
    value = PASS_ASSIGN_RE.sub(r"\1=[REDACTED]", value)
    # Keep domain-like tokens for security value; redact full emails by default
    value = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    return value


def scrub(obj: Any, *, keep_ips: bool = True) -> Any:
    """Return a deep-copied structure with PII/secrets removed."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower().replace("-", "_")
            if lk in SENSITIVE_KEYS or any(s in lk for s in ("password", "secret", "token", "email_body")):
                out[k] = "[REDACTED]"
                continue
            if not keep_ips and lk in {
                "src_ip",
                "dst_ip",
                "source_ip",
                "destination_ip",
                "local_ip",
                "ip_address",
            }:
                out[k] = "[REDACTED_IP]"
                continue
            out[k] = scrub(v, keep_ips=keep_ips)
        return out
    if isinstance(obj, list):
        return [scrub(x, keep_ips=keep_ips) for x in obj]
    if isinstance(obj, str):
        return _scrub_string(obj)
    return copy.deepcopy(obj)


def to_cloud_alert(event: dict[str, Any]) -> dict[str, Any]:
    """
    Map a local engine event to the safe cloud telemetry contract
    (aligned with KB-057 field set — no raw payloads / IPs by default).
    """
    clean = scrub(event, keep_ips=False)
    severity = str(
        clean.get("severity")
        or clean.get("rule", {}).get("level")
        or "medium"
    ).lower()
    if severity.isdigit():
        lvl = int(severity)
        severity = "critical" if lvl >= 12 else "high" if lvl >= 10 else "medium" if lvl >= 7 else "low"
    if severity not in {"low", "medium", "high", "critical"}:
        severity = "medium"

    title = (
        clean.get("alert_title")
        or clean.get("rule", {}).get("description")
        or clean.get("note")
        or clean.get("event_type")
        or "Security alert"
    )
    source_tool = str(
        clean.get("source_tool")
        or clean.get("decoder", {}).get("name")
        or clean.get("agent", {}).get("name")
        or "appliance"
    )[:100]
    external_id = str(
        clean.get("external_alert_id")
        or clean.get("id")
        or clean.get("uuid")
        or clean.get("timestamp")
        or "unknown"
    )[:255]

    return {
        "source_tool": source_tool,
        "external_alert_id": external_id,
        "severity": severity,
        "alert_title": str(title)[:500],
        "alert_description": str(clean.get("alert_description") or clean.get("full_log") or "")[:4000]
        or None,
        "event_time": clean.get("event_time") or clean.get("timestamp"),
        "destination_host": clean.get("destination_host")
        or (clean.get("agent") or {}).get("name"),
    }
