"""KB-091: Deterministic SOC field synthesis (no AI worker required)."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


def _raw_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("raw_event")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _rule_from_raw(raw: Dict[str, Any]) -> Dict[str, Any]:
    rule = raw.get("rule")
    return rule if isinstance(rule, dict) else {}


def _agent_from_raw(raw: Dict[str, Any]) -> Dict[str, Any]:
    agent = raw.get("agent")
    return agent if isinstance(agent, dict) else {}


def _eventdata_from_raw(raw: Dict[str, Any]) -> Dict[str, Any]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    win = data.get("win") if isinstance(data.get("win"), dict) else {}
    eventdata = win.get("eventdata") if isinstance(win.get("eventdata"), dict) else {}
    return eventdata if isinstance(eventdata, dict) else {}


def _syscheck_from_raw(raw: Dict[str, Any]) -> Dict[str, Any]:
    syscheck = raw.get("syscheck")
    return syscheck if isinstance(syscheck, dict) else {}


def _str_or_none(value: Any, limit: int = 4000) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _parse_hashes(value: Any) -> tuple[Optional[str], Optional[str]]:
    md5 = None
    sha256 = None
    if not value:
        return md5, sha256
    text = str(value).strip()
    for part in text.split(","):
        piece = part.strip()
        if "=" in piece:
            key, raw_val = piece.split("=", 1)
            key = key.strip().lower()
            raw_val = raw_val.strip().lower()
            if key == "md5" and len(raw_val) == 32:
                md5 = raw_val
            if key == "sha256" and len(raw_val) == 64:
                sha256 = raw_val
        else:
            low = piece.lower()
            if len(low) == 32:
                md5 = low
            if len(low) == 64:
                sha256 = low
    return md5, sha256


def extract_mac_from_raw(raw: Dict[str, Any]) -> Optional[str]:
    agent = _agent_from_raw(raw)
    for key in ("mac", "mac_address", "Mac"):
        val = agent.get(key)
        if val:
            return str(val)[:64]
    eventdata = _eventdata_from_raw(raw)
    for key in ("MacAddress", "mac", "mac_address"):
        val = eventdata.get(key)
        if val:
            return str(val)[:64]
    return None


def extract_os_from_raw(raw: Dict[str, Any]) -> Optional[str]:
    agent = _agent_from_raw(raw)
    os_info = agent.get("os")
    if isinstance(os_info, dict):
        name = str(os_info.get("name") or "").strip()
        version = str(os_info.get("version") or "").strip()
        combined = f"{name} {version}".strip()
        return combined[:255] if combined else None
    if isinstance(os_info, str) and os_info.strip():
        return os_info.strip()[:255]
    return None


def extract_wazuh_rule_id(raw: Dict[str, Any]) -> Optional[str]:
    rule = _rule_from_raw(raw)
    rid = rule.get("id")
    return str(rid) if rid is not None else None


def _clean_ip(value: Any) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    return text or None


def build_asset_context(row: Dict[str, Any]) -> Dict[str, Any]:
    """Endpoint / inventory context for admin alert & incident panels."""
    raw = _raw_dict(row)
    agent = _agent_from_raw(raw)

    details = row.get("asset_details")
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except (TypeError, ValueError):
            details = {}
    if not isinstance(details, dict):
        details = {}

    ip = _clean_ip(
        row.get("asset_ip") or row.get("destination_ip") or row.get("source_ip") or agent.get("ip")
    )
    mac = (
        details.get("mac_address")
        or details.get("mac")
        or extract_mac_from_raw(raw)
    )
    os_name = (
        (row.get("asset_os_name") or "").strip()
        or extract_os_from_raw(raw)
        or None
    )

    location_parts: list[str] = []
    tenant_name = (row.get("tenant_name") or "").strip()
    tz = (row.get("tenant_timezone") or "").strip()
    if tenant_name:
        location_parts.append(tenant_name)
    if tz:
        location_parts.append(f"TZ {tz}")

    return {
        "asset_criticality": (row.get("asset_criticality") or "medium").strip(),
        "asset_location": " · ".join(location_parts) if location_parts else None,
        "display_ip_address": ip,
        "display_operating_system": os_name,
        "display_mac_address": str(mac)[:64] if mac else None,
        "asset_owner": (row.get("asset_owner") or "").strip() or None,
        "wazuh_rule_id": extract_wazuh_rule_id(raw),
        "wazuh_agent_id": (
            str(details.get("wazuh_agent_id") or agent.get("id") or "").strip() or None
        ),
    }


def build_alert_evidence(row: Dict[str, Any]) -> Dict[str, Any]:
    """Extract customer-safe forensic detail from stored alert payloads."""
    raw = _raw_dict(row)
    rule = _rule_from_raw(raw)
    syscheck = _syscheck_from_raw(raw)
    eventdata = _eventdata_from_raw(raw)
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}

    file_path = _str_or_none(
        syscheck.get("path")
        or eventdata.get("TargetFilename") or eventdata.get("targetFilename")
        or eventdata.get("FilePath") or eventdata.get("filePath")
        or data.get("path")
        or raw.get("path"),
        1000,
    )
    process_name = _str_or_none(
        eventdata.get("Image") or eventdata.get("image")
        or eventdata.get("process_name") or data.get("process_name"),
        500,
    )
    parent_process_name = _str_or_none(
        eventdata.get("ParentImage") or eventdata.get("parentImage")
        or eventdata.get("parent_process_name")
        or data.get("parent_process_name"),
        500,
    )
    command_line = _str_or_none(
        eventdata.get("CommandLine") or eventdata.get("commandLine")
        or eventdata.get("command_line") or data.get("command_line"),
        4000,
    )
    parent_command_line = _str_or_none(
        eventdata.get("ParentCommandLine") or eventdata.get("parentCommandLine")
        or eventdata.get("parent_command_line")
        or data.get("parent_command_line"),
        4000,
    )
    hash_md5, hash_sha256 = _parse_hashes(
        eventdata.get("Hashes") or eventdata.get("hashes")
        or syscheck.get("sha256") or syscheck.get("md5")
    )
    if not hash_md5:
        hash_md5 = _str_or_none(syscheck.get("md5") or data.get("md5"), 32)
    if not hash_sha256:
        hash_sha256 = _str_or_none(
            syscheck.get("sha256")
            or data.get("sha256")
            or eventdata.get("sha256")
            or eventdata.get("Sha256"),
            64,
        )
    file_name = _str_or_none(
        syscheck.get("filename")
        or eventdata.get("FileName")
        or eventdata.get("fileName")
        or eventdata.get("TargetFilename")
        or eventdata.get("targetFilename"),
        255,
    )
    if file_name and ("/" in file_name or "\\" in file_name):
        file_name = file_name.replace("\\", "/").rsplit("/", 1)[-1][:255]
    if not file_name and file_path:
        file_name = file_path.replace("\\", "/").rsplit("/", 1)[-1][:255]

    mitre = row.get("mitre_mapping")
    if isinstance(mitre, str):
        try:
            mitre = json.loads(mitre)
        except (TypeError, ValueError):
            mitre = {}
    if not isinstance(mitre, dict):
        mitre = {}
    tactics = mitre.get("tactics") if isinstance(mitre.get("tactics"), list) else []
    techniques = mitre.get("techniques") if isinstance(mitre.get("techniques"), list) else []

    technique_values: list[str] = []
    for item in techniques[:10]:
        if isinstance(item, dict):
            value = str(item.get("id") or item.get("name") or "").strip()
        else:
            value = str(item).strip()
        if value:
            technique_values.append(value[:160])

    return {
        "wazuh_rule_id": extract_wazuh_rule_id(raw),
        "wazuh_rule_level": _str_or_none(rule.get("level"), 16),
        "file_path": file_path,
        "file_name": file_name,
        "process_name": process_name,
        "parent_process_name": parent_process_name,
        "command_line": command_line,
        "parent_command_line": parent_command_line,
        "hash_md5": hash_md5,
        "hash_sha256": hash_sha256,
        "mitre_tactics": [str(x)[:120] for x in tactics[:10] if str(x).strip()],
        "mitre_techniques": technique_values,
    }


def synthesize_soc_guidance(row: Dict[str, Any]) -> Dict[str, str]:
    """
    Rule-driven SOC copy for business impact / recommended action / attack type.
    Used when AI worker fields are empty.
    """
    raw = _raw_dict(row)
    rule = _rule_from_raw(raw)
    mitre = row.get("mitre_mapping")
    if isinstance(mitre, str):
        try:
            mitre = json.loads(mitre)
        except (TypeError, ValueError):
            mitre = {}
    if not isinstance(mitre, dict):
        mitre = {}

    title = str(row.get("alert_title") or "").strip()
    title_lower = title.lower()
    severity = str(row.get("severity") or "medium").lower()
    status = str(row.get("status") or "").lower()
    rule_id = str(rule.get("id") or "")

    techniques = mitre.get("techniques") or []
    tactics = mitre.get("tactics") or []
    likely_parts: list[str] = []
    for tech in techniques[:4]:
        if isinstance(tech, dict):
            tid = str(tech.get("id") or "").strip()
            name = str(tech.get("name") or "").strip()
            if tid and name:
                likely_parts.append(f"{tid} {name}")
            elif name:
                likely_parts.append(name)
    if tactics and not likely_parts:
        likely_parts.append(f"MITRE tactics: {', '.join(str(t) for t in tactics[:4])}")

    if not likely_parts:
        if "powershell" in title_lower:
            likely_parts.append("T1059.001 PowerShell")
        elif "file dropped" in title_lower or "malware" in title_lower:
            likely_parts.append("T1105 Ingress tool transfer / suspicious file drop")
        elif rule_id == "92057":
            likely_parts.append("T1059.001 Suspicious PowerShell execution")

    likely_attack = "; ".join(likely_parts) if likely_parts else (
        f"Rule {rule_id} — {title[:120]}" if rule_id else title[:160]
    )

    if status == "false_positive":
        business_impact = (
            "Classified as expected operational noise after SOC review. "
            "No confirmed unauthorized activity on the monitored endpoint."
        )
        recommended_action = (
            "No customer action required. Retain for tuning reference; "
            "Phase-1 suppress/correlate rules should prevent repeat incident floods."
        )
    elif severity == "critical":
        business_impact = (
            "Critical detection on a monitored endpoint — potential unauthorized code execution, "
            "persistence, or defense evasion. Validate immediately to prevent spread or data impact."
        )
        recommended_action = (
            "Confirm process/file lineage on the host, check for lateral movement, "
            "and contain (kill/isolate) if unauthorized. Document outcome in incident timeline."
        )
    elif severity == "high":
        business_impact = (
            "High-severity security event requiring analyst validation. "
            "May indicate policy violation or early-stage attack activity."
        )
        recommended_action = (
            "Review host, user, and file/process evidence. Escalate to incident if unauthorized."
        )
    else:
        business_impact = (
            "Security event logged for SOC review. Impact depends on validation of host and user context."
        )
        recommended_action = "Triage alert, correlate with adjacent events, and close or escalate as needed."

    if rule_id == "92213" or "file dropped" in title_lower:
        recommended_action = (
            "Inspect target path and hash. If path contains __PSScriptPolicyTest_ during elevated "
            "PowerShell or AR remedi install, mark false positive. Otherwise quarantine file and hunt."
        )
    if rule_id == "92057" or "powershell" in title_lower:
        recommended_action = (
            "Review parent/child process tree and command line. Confirm authorized admin or "
            "approved change activity before closing."
        )

    return {
        "likely_attack_type": likely_attack[:4000],
        "business_impact": business_impact[:4000],
        "recommended_action": recommended_action[:4000],
    }


def apply_soc_enrichment(row: Dict[str, Any]) -> Dict[str, Any]:
    """Attach asset context + fill empty SOC guidance fields on a row copy."""
    out = dict(row)
    ctx = build_asset_context(out)
    out.update(ctx)
    out.update(build_alert_evidence(out))

    synth = synthesize_soc_guidance(out)
    if not (out.get("ai_likely_attack_type") or "").strip():
        out["ai_likely_attack_type"] = synth["likely_attack_type"]
    if not (out.get("ai_business_impact") or "").strip():
        out["ai_business_impact"] = synth["business_impact"]
    if not (out.get("ai_recommended_action") or "").strip():
        out["ai_recommended_action"] = synth["recommended_action"]

    # Friendly fallbacks for empty display fields
    if not out.get("display_mac_address"):
        out["display_mac_address"] = None
        out["mac_address_status"] = "Not reported by agent inventory yet"
    else:
        out["mac_address_status"] = None

    return out
