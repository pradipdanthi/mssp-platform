"""Wazuh / Sysmon alert telemetry extraction for ingest + read paths."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple

_KV_LINE_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9_.\-\s]{0,80}?):\s+(.+?)\s*$",
    re.MULTILINE,
)
_GUID_RE = re.compile(
    r"\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}"
)


def _str_or_none(value: Any, limit: int = 4000) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


def _first(*values: Any) -> Optional[str]:
    for value in values:
        got = _str_or_none(value)
        if got:
            return got
    return None


def _raw_dict(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return {}
    return raw if isinstance(raw, dict) else {}


def _eventdata_from_raw(raw: Dict[str, Any]) -> Dict[str, Any]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    win = data.get("win") if isinstance(data.get("win"), dict) else {}
    eventdata = win.get("eventdata") if isinstance(win.get("eventdata"), dict) else {}
    if eventdata:
        return dict(eventdata)
    sysmon = data.get("sysmon") if isinstance(data.get("sysmon"), dict) else {}
    if sysmon:
        return dict(sysmon)
    return {}


def _full_log_text(raw: Dict[str, Any]) -> str:
    for key in ("full_log", "message", "log"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    for key in ("full_log", "message"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def parse_hash_triplet(value: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse MD5=..., SHA256=..., IMPHASH=... from Wazuh Hashes field."""
    md5 = sha256 = imphash = None
    if not value:
        return md5, sha256, imphash
    text = str(value).strip()
    for part in text.split(","):
        piece = part.strip()
        if "=" in piece:
            key, raw_val = piece.split("=", 1)
            key = key.strip().lower()
            raw_val = raw_val.strip().lower()
            if key == "md5" and len(raw_val) == 32:
                md5 = raw_val
            elif key in ("sha256", "sha-256") and len(raw_val) == 64:
                sha256 = raw_val
            elif key in ("imphash", "imp") and len(raw_val) == 32:
                imphash = raw_val
        else:
            low = piece.lower()
            if len(low) == 32 and not md5:
                md5 = low
            if len(low) == 64:
                sha256 = low
    return md5, sha256, imphash


def regex_kv_fallback(*texts: str) -> Dict[str, str]:
    """Extract Key: Value pairs from legacy Wazuh full_log / description text."""
    out: Dict[str, str] = {}
    for text in texts:
        if not text:
            continue
        for match in _KV_LINE_RE.finditer(text):
            key = match.group(1).strip()
            val = match.group(2).strip()
            if key and val and key not in out:
                out[key] = val[:2000]
    return out


def parse_wazuh_alert_telemetry(
    raw: Any,
    *,
    alert_description: str = "",
) -> Dict[str, Any]:
    """
    Extract structured telemetry from a Wazuh alert payload.

    Returns a dict suitable for UPDATE security_alerts SET ... including
    win_eventdata, wazuh_full_log, mapped scalar columns, and hash_* fields.
    """
    raw_obj = _raw_dict(raw)
    eventdata = dict(_eventdata_from_raw(raw_obj))
    full_log = _full_log_text(raw_obj)
    desc = (alert_description or raw_obj.get("description") or "").strip()

    if not eventdata:
        fallback = regex_kv_fallback(full_log, desc)
        if fallback:
            eventdata = fallback

    hashes_raw = _first(
        eventdata.get("Hashes"),
        eventdata.get("hashes"),
        eventdata.get("Hash"),
    )
    md5, sha256, imphash = parse_hash_triplet(hashes_raw)

    process_name = _first(
        eventdata.get("Image"),
        eventdata.get("image"),
        eventdata.get("process_name"),
    )
    parent_process = _first(
        eventdata.get("ParentImage"),
        eventdata.get("parentImage"),
        eventdata.get("parentProcess"),
        eventdata.get("parent_process"),
    )
    command_line = _first(
        eventdata.get("CommandLine"),
        eventdata.get("commandLine"),
        eventdata.get("command_line"),
    )
    parent_command_line = _first(
        eventdata.get("ParentCommandLine"),
        eventdata.get("parentCommandLine"),
        eventdata.get("parent_command_line"),
    )

    wazuh_full_log: Dict[str, Any] = {}
    if full_log:
        wazuh_full_log = {"text": full_log[:50000]}
    elif desc and not eventdata:
        wazuh_full_log = {"text": desc[:50000]}

    return {
        "win_eventdata": eventdata,
        "wazuh_full_log": wazuh_full_log,
        "process_name": process_name,
        "parent_process": parent_process,
        "parent_command_line": parent_command_line,
        "command_line": command_line,
        "current_directory": _first(
            eventdata.get("CurrentDirectory"),
            eventdata.get("currentDirectory"),
        ),
        "integrity_level": _first(
            eventdata.get("IntegrityLevel"),
            eventdata.get("integrityLevel"),
        ),
        "process_guid": _first(
            eventdata.get("ProcessGuid"),
            eventdata.get("processGuid"),
        ),
        "parent_process_guid": _first(
            eventdata.get("ParentProcessGuid"),
            eventdata.get("parentProcessGuid"),
        ),
        "logon_id": _first(
            eventdata.get("LogonId"),
            eventdata.get("logonId"),
            eventdata.get("TargetLogonId"),
        ),
        "logon_guid": _first(
            eventdata.get("LogonGuid"),
            eventdata.get("logonGuid"),
        ),
        "user_sid": _first(
            eventdata.get("SubjectUserSid"),
            eventdata.get("UserSid"),
            eventdata.get("TargetUserSid"),
            eventdata.get("SubjectUserName"),
            eventdata.get("User"),
        ),
        "process_id": _first(
            eventdata.get("ProcessId"),
            eventdata.get("processId"),
        ),
        "parent_process_id": _first(
            eventdata.get("ParentProcessId"),
            eventdata.get("parentProcessId"),
        ),
        "hashes_raw": hashes_raw,
        "hash_md5": md5,
        "hash_sha256": sha256,
        "hash_imphash": imphash,
    }


def persist_alert_telemetry(
    cur: Any,
    *,
    alert_id: str,
    tenant_id: str,
    raw: Any,
    alert_description: str = "",
) -> Dict[str, Any]:
    """Parse telemetry and persist onto security_alerts (ingest path)."""
    telemetry = parse_wazuh_alert_telemetry(raw, alert_description=alert_description)
    cur.execute(
        """
        UPDATE security_alerts
        SET win_eventdata = %s::jsonb,
            wazuh_full_log = %s::jsonb,
            parent_process = %s,
            parent_command_line = %s,
            current_directory = %s,
            integrity_level = %s,
            process_guid = %s,
            parent_process_guid = %s,
            logon_id = %s,
            logon_guid = %s,
            hashes_raw = %s,
            hash_md5 = %s,
            hash_sha256 = %s,
            hash_imphash = %s,
            process_id = %s,
            parent_process_id = %s,
            user_sid = %s,
            updated_at = now()
        WHERE id = %s::uuid AND tenant_id = %s::uuid;
        """,
        (
            json.dumps(telemetry.get("win_eventdata") or {}),
            json.dumps(telemetry.get("wazuh_full_log") or {}),
            telemetry.get("parent_process"),
            telemetry.get("parent_command_line"),
            telemetry.get("current_directory"),
            telemetry.get("integrity_level"),
            telemetry.get("process_guid"),
            telemetry.get("parent_process_guid"),
            telemetry.get("logon_id"),
            telemetry.get("logon_guid"),
            telemetry.get("hashes_raw"),
            telemetry.get("hash_md5"),
            telemetry.get("hash_sha256"),
            telemetry.get("hash_imphash"),
            telemetry.get("process_id"),
            telemetry.get("parent_process_id"),
            telemetry.get("user_sid"),
            alert_id,
            tenant_id,
        ),
    )
    return telemetry


def telemetry_for_api_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Merge persisted telemetry columns with live parse fallback for API responses."""
    parsed = parse_wazuh_alert_telemetry(
        row.get("raw_event"),
        alert_description=str(row.get("alert_description") or ""),
    )
    win_eventdata = row.get("win_eventdata")
    if isinstance(win_eventdata, str):
        try:
            win_eventdata = json.loads(win_eventdata)
        except (TypeError, ValueError):
            win_eventdata = {}
    if not isinstance(win_eventdata, dict) or not win_eventdata:
        win_eventdata = parsed.get("win_eventdata") or {}

    wazuh_full_log = row.get("wazuh_full_log")
    if isinstance(wazuh_full_log, str):
        try:
            wazuh_full_log = json.loads(wazuh_full_log)
        except (TypeError, ValueError):
            wazuh_full_log = {}
    if not isinstance(wazuh_full_log, dict):
        wazuh_full_log = parsed.get("wazuh_full_log") or {}

    def pick(col: str, *parsed_keys: str) -> Optional[str]:
        val = row.get(col)
        if val:
            return _str_or_none(val)
        for key in parsed_keys:
            got = parsed.get(key)
            if got:
                return got
        return None

    return {
        "win_eventdata": win_eventdata,
        "wazuh_full_log": wazuh_full_log,
        "parent_process": pick("parent_process", "parent_process"),
        "parent_command_line": pick("parent_command_line", "parent_command_line"),
        "current_directory": pick("current_directory", "current_directory"),
        "integrity_level": pick("integrity_level", "integrity_level"),
        "process_guid": pick("process_guid", "process_guid"),
        "parent_process_guid": pick("parent_process_guid", "parent_process_guid"),
        "logon_id": pick("logon_id", "logon_id"),
        "logon_guid": pick("logon_guid", "logon_guid"),
        "user_sid": pick("user_sid", "user_sid"),
        "process_id": pick("process_id", "process_id"),
        "parent_process_id": pick("parent_process_id", "parent_process_id"),
        "hashes_raw": pick("hashes_raw", "hashes_raw"),
        "hash_imphash": pick("hash_imphash", "hash_imphash"),
        "process_name": pick("process_name", "process_name") or parsed.get("process_name"),
        "command_line": pick("command_line", "command_line") or parsed.get("command_line"),
        "hash_md5": pick("hash_md5", "hash_md5") or parsed.get("hash_md5"),
        "hash_sha256": pick("hash_sha256", "hash_sha256") or parsed.get("hash_sha256"),
    }
