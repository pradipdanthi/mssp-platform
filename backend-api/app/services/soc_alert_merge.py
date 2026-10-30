"""Occurrence merge for identical SOC detections.

Production rules (audit + SLA):
  * Merge only the same tenant, source, rule, host, and behaviour.
  * Different CVEs, hosts, files, hashes, or processes stay separate.
  * Every engine id is stored on security_alert_occurrences; nothing is deleted.
  * first_seen_at and created_at never move (SLA clock).
  * last_seen_at / occurrence_count record continuation.
  * Closed or false-positive parents do not absorb a later hit — a new alert
    is opened (new SLA) and linked via recurrence_of_alert_id.
  * Severity only rises.
  * Customer notification and TIA enqueue happen on the first open alert only.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Optional

from app.schemas.soc_sync import SocSyncRequest

OPEN_MERGE_STATUSES = ("new", "triaged", "incident_created")
TERMINAL_STATUSES = ("closed", "false_positive")
_SEV_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_CVE_RE = re.compile(r"(CVE-\d{4}-\d+)", re.I)
_RULE_RE = re.compile(r"Wazuh rule\s+(\d+)", re.I)
_KV_RE = re.compile(r"\b(image|target_file|sha256|hash_sha256|user|cmdline)=([^;]+)", re.I)


def higher_severity(left: Optional[str], right: Optional[str]) -> str:
    a = (left or "low").lower()
    b = (right or "low").lower()
    return a if _SEV_RANK.get(a, 0) >= _SEV_RANK.get(b, 0) else b


def _norm(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _kv(blob: str, key: str) -> str:
    for match in _KV_RE.finditer(blob or ""):
        if match.group(1).lower() == key.lower():
            return match.group(2).strip()
    return ""


def extract_cve(*texts: Optional[str]) -> str:
    for text in texts:
        match = _CVE_RE.search(text or "")
        if match:
            return match.group(1).upper()
    return ""


def extract_rule_id(payload: SocSyncRequest) -> str:
    rid = (payload.rule_id or "").strip()
    if rid:
        return rid
    blob = " ".join(
        filter(None, [payload.alert_description, payload.technical_summary])
    )
    match = _RULE_RE.search(blob)
    return match.group(1) if match else ""


def behaviour_key(payload: SocSyncRequest) -> str:
    """What makes two events the same story on one host.

    Prefer a file hash, then process+file, then CVE, then title. Empty
    discriminators collapse to title so two unnamed repeats can still merge.
    """
    tech = payload.technical_summary or ""
    sha = _norm(_kv(tech, "sha256") or _kv(tech, "hash_sha256"))
    if sha:
        return f"sha256:{sha}"
    image = _norm(_kv(tech, "image"))
    target = _norm(_kv(tech, "target_file"))
    user = _norm(payload.source_user) or _norm(_kv(tech, "user"))
    if image or target:
        return f"image:{image}|file:{target}|user:{user}"
    cve = extract_cve(payload.alert_title, payload.alert_description, tech)
    if cve:
        return f"cve:{cve}"
    title = _norm(payload.alert_title)
    return f"title:{title}" if title else ""


def merge_fingerprint(payload: SocSyncRequest) -> Optional[str]:
    """Stable key or None when the event must not merge (fail closed)."""
    host = _norm(payload.destination_host)
    rule = extract_rule_id(payload)
    behaviour = behaviour_key(payload)
    source = _norm(payload.source_tool) or "wazuh"
    if not host or not rule or not behaviour:
        return None
    raw = f"{source}|{rule}|{host}|{behaviour}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"{raw}|{digest}"


def occurrence_summary(payload: SocSyncRequest) -> str:
    host = payload.destination_host or "n/a"
    return (
        f"{payload.source_tool}:{payload.external_alert_id} "
        f"host={host} title={payload.alert_title}"
    )[:500]


def audit_details(
    *,
    parent_id: str,
    occurrence_no: int,
    payload: SocSyncRequest,
    fingerprint: str,
    sla_first_seen_preserved: bool,
) -> Dict[str, Any]:
    return {
        "parent_alert_id": parent_id,
        "occurrence_no": occurrence_no,
        "source_tool": payload.source_tool,
        "external_alert_id": payload.external_alert_id,
        "rule_id": extract_rule_id(payload) or None,
        "host": payload.destination_host,
        "fingerprint": fingerprint,
        "sla_first_seen_preserved": sla_first_seen_preserved,
        "severity": payload.severity,
    }
