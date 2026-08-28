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
    clean = scrub(event, keep_ips=True)
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
    # Prefer explicit source_tool; never use agent hostname as the tool name.
    decoder = clean.get("decoder") if isinstance(clean.get("decoder"), dict) else {}
    source_tool = str(
        clean.get("source_tool")
        or ("wazuh" if clean.get("rule") or clean.get("agent") else None)
        or decoder.get("name")
        or "appliance"
    )[:100]
    external_id = str(
        clean.get("external_alert_id")
        or clean.get("id")
        or clean.get("uuid")
        or clean.get("timestamp")
        or "unknown"
    )[:255]
    agent = clean.get("agent") if isinstance(clean.get("agent"), dict) else {}
    host = clean.get("destination_host") or agent.get("name")

    description = clean.get("alert_description")
    if not description:
        parts = []
        rule = clean.get("rule") if isinstance(clean.get("rule"), dict) else {}
        if rule.get("id") is not None:
            parts.append(f"rule={rule.get('id')}")
        if rule.get("level") is not None:
            parts.append(f"level={rule.get('level')}")
        if agent.get("name"):
            parts.append(f"agent={agent.get('name')}")
        description = "; ".join(parts) if parts else None

    rule = clean.get("rule") if isinstance(clean.get("rule"), dict) else {}
    mitre = rule.get("mitre") if isinstance(rule.get("mitre"), dict) else {}
    data = clean.get("data") if isinstance(clean.get("data"), dict) else {}
    syscheck = clean.get("syscheck") if isinstance(clean.get("syscheck"), dict) else {}
    win = data.get("win") if isinstance(data.get("win"), dict) else {}
    eventdata = win.get("eventdata") if isinstance(win.get("eventdata"), dict) else {}

    source_ip = (
        clean.get("source_ip")
        or data.get("srcip")
        or data.get("src_ip")
        or eventdata.get("SourceIp")
        or eventdata.get("IpAddress")
    )
    destination_ip = (
        clean.get("destination_ip")
        or data.get("dstip")
        or data.get("dst_ip")
        or eventdata.get("DestinationIp")
    )
    source_user = (
        clean.get("source_user")
        or data.get("srcuser")
        or eventdata.get("User")
        or eventdata.get("TargetUserName")
        or eventdata.get("SubjectUserName")
    )

    mitre_mapping = {
        "tactics": mitre.get("tactic") or mitre.get("tactics") or [],
        "techniques": mitre.get("id") or mitre.get("technique") or mitre.get("techniques") or [],
    }

    rich_event = {
        "agent": agent,
        "rule": rule,
        "decoder": decoder,
        "data": data,
        "syscheck": syscheck,
        "timestamp": clean.get("timestamp"),
        "location": clean.get("location"),
    }

    # Optional appliance-local AI triage annotation (never required by ingest).
    appliance_ai = clean.get("appliance_ai")
    if isinstance(appliance_ai, dict) and appliance_ai:
        rich_event["appliance_ai"] = {
            "verdict": str(appliance_ai.get("verdict") or "")[:64] or None,
            "confidence": appliance_ai.get("confidence"),
            "summary": str(appliance_ai.get("summary") or "")[:2000] or None,
            "recommended_action": str(appliance_ai.get("recommended_action") or "")[:64]
            or None,
            "reason": str(appliance_ai.get("reason") or "")[:256] or None,
            "model": str(appliance_ai.get("model") or "")[:128] or None,
            "filter": str(appliance_ai.get("filter") or "local_ai_v1")[:64],
        }
        # Drop empty keys for a clean payload.
        rich_event["appliance_ai"] = {
            k: v for k, v in rich_event["appliance_ai"].items() if v is not None
        }

    out: dict[str, Any] = {
        "source_tool": source_tool,
        "external_alert_id": external_id,
        "severity": severity,
        "alert_title": str(title)[:500],
        "alert_description": (str(description)[:4000] if description else None),
        "event_time": clean.get("event_time") or clean.get("timestamp"),
        "destination_host": str(host)[:255] if host else None,
        "source_ip": str(source_ip)[:64] if source_ip else None,
        "destination_ip": str(destination_ip)[:64] if destination_ip else None,
        "source_user": str(source_user)[:255] if source_user else None,
        "raw_event": rich_event,
        "mitre_mapping": mitre_mapping,
    }
    # Top-level optional fields for control-plane convenience (ignored if schema
    # forbids extras; also mirrored under raw_event.appliance_ai).
    if isinstance(appliance_ai, dict) and appliance_ai.get("verdict"):
        out["appliance_ai_verdict"] = str(appliance_ai.get("verdict"))[:64]
        try:
            out["appliance_ai_confidence"] = float(appliance_ai.get("confidence"))
        except (TypeError, ValueError):
            pass
        if appliance_ai.get("summary"):
            out["appliance_ai_summary"] = str(appliance_ai.get("summary"))[:2000]
    return out
