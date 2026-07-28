"""KB-084: Normalize Sysmon / Osquery / Auditd process creation into process trees."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.edr import ProcessTreeNode, ProcessTreeResponse

# Heuristic signed binaries (Windows well-known + Linux package paths).
_SIGNED_HINTS = (
    r"\\windows\\system32\\",
    r"\\windows\\syswow64\\",
    r"\\program files\\",
    r"/usr/bin/",
    r"/usr/sbin/",
    r"/bin/",
    r"/sbin/",
)


def _int_or_none(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any, limit: int = 500) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:limit]


def _parse_hashes(raw: Any) -> Tuple[Optional[str], Optional[str]]:
    """Parse Sysmon Hashes=MD5=..,SHA256=.. or discrete fields."""
    md5 = sha256 = None
    if isinstance(raw, dict):
        md5 = _str_or_none(raw.get("md5") or raw.get("MD5"), 32)
        sha256 = _str_or_none(raw.get("sha256") or raw.get("SHA256"), 64)
        return md5, sha256
    text = str(raw or "")
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip().upper()
            v = v.strip().lower()
            if k == "MD5" and re.fullmatch(r"[a-f0-9]{32}", v):
                md5 = v
            elif k in ("SHA256", "SHA-256") and re.fullmatch(r"[a-f0-9]{64}", v):
                sha256 = v
        elif re.fullmatch(r"[a-f0-9]{64}", part.lower()):
            sha256 = part.lower()
        elif re.fullmatch(r"[a-f0-9]{32}", part.lower()):
            md5 = part.lower()
    return md5, sha256


def _signed_status(image: Optional[str], explicit: Any = None) -> Optional[str]:
    if explicit is not None and str(explicit).strip():
        val = str(explicit).strip().lower()
        if val in ("signed", "valid", "trusted", "true", "1"):
            return "signed"
        if val in ("unsigned", "invalid", "untrusted", "false", "0"):
            return "unsigned"
    if not image:
        return "unknown"
    low = image.lower()
    for hint in _SIGNED_HINTS:
        if hint in low:
            return "likely_signed"
    return "unknown"


def _parse_event_time(raw: Dict[str, Any], eventdata: Dict[str, Any]) -> Optional[datetime]:
    for key in ("UtcTime", "utc_time", "timestamp", "@timestamp", "event_time"):
        val = eventdata.get(key) or raw.get(key)
        if not val:
            continue
        try:
            s = str(val).replace("Z", "+00:00")
            return datetime.fromisoformat(s)
        except ValueError:
            continue
    return None


def _mitre_tags(raw: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    rule = raw.get("rule") if isinstance(raw.get("rule"), dict) else {}
    mitre = rule.get("mitre") if isinstance(rule.get("mitre"), list) else []
    for item in mitre:
        if isinstance(item, dict):
            tid = item.get("id") or item.get("technique_id")
            if tid:
                tags.append(str(tid))
        elif item:
            tags.append(str(item))
    mapping = raw.get("mitre_mapping") if isinstance(raw.get("mitre_mapping"), dict) else {}
    for tech in mapping.get("techniques") or []:
        if isinstance(tech, dict) and tech.get("id"):
            tags.append(str(tech["id"]))
        elif isinstance(tech, str):
            tags.append(tech)
    # Dedupe preserving order
    seen = set()
    out: List[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:20]


def normalize_process_event(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract one normalized process-creation dict from a raw engine event.
    Customer APIs never expose engine product names; raw_source is internal only.
    """
    if not isinstance(raw, dict):
        return None
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    rule = raw.get("rule") if isinstance(raw.get("rule"), dict) else {}
    groups = [str(g).lower() for g in (rule.get("groups") or []) if g]
    blob = str(raw).lower()

    agent = raw.get("agent") if isinstance(raw.get("agent"), dict) else {}
    agent_id = _str_or_none(agent.get("id"), 64)

    # --- Sysmon Event ID 1 style ---
    win = data.get("win") if isinstance(data.get("win"), dict) else {}
    eventdata = win.get("eventdata") if isinstance(win.get("eventdata"), dict) else {}
    if not eventdata and isinstance(data.get("eventdata"), dict):
        eventdata = data["eventdata"]
    system = win.get("system") if isinstance(win.get("system"), dict) else {}
    sysmon_id = _str_or_none(
        eventdata.get("EventID") or system.get("eventID") or data.get("EventID"),
        8,
    )
    is_sysmon = (
        "sysmon" in groups
        or "sysmon" in blob
        or bool(eventdata.get("ProcessGuid") or eventdata.get("Image"))
    )
    if is_sysmon and (eventdata.get("Image") or eventdata.get("ProcessId")):
        md5, sha256 = _parse_hashes(eventdata.get("Hashes") or eventdata.get("hashes"))
        if not sha256:
            _, sha256 = _parse_hashes(eventdata.get("sha256"))
        image = _str_or_none(eventdata.get("Image") or eventdata.get("process_name"), 500)
        return {
            "pid": _int_or_none(eventdata.get("ProcessId") or eventdata.get("process_id")),
            "parent_pid": _int_or_none(
                eventdata.get("ParentProcessId") or eventdata.get("parent_process_id")
            ),
            "process_guid": _str_or_none(eventdata.get("ProcessGuid"), 128),
            "parent_process_guid": _str_or_none(eventdata.get("ParentProcessGuid"), 128),
            "process_name": image,
            "parent_process_name": _str_or_none(
                eventdata.get("ParentImage") or eventdata.get("parent_image"), 500
            ),
            "command_line": _str_or_none(
                eventdata.get("CommandLine") or eventdata.get("command_line"), 4000
            ),
            "parent_command_line": _str_or_none(
                eventdata.get("ParentCommandLine") or eventdata.get("parent_command_line"),
                4000,
            ),
            "username": _str_or_none(eventdata.get("User") or eventdata.get("user"), 255),
            "hash_md5": md5,
            "hash_sha256": sha256,
            "signed_status": _signed_status(image, eventdata.get("Signed")),
            "event_time": _parse_event_time(raw, eventdata),
            "mitre_techniques": _mitre_tags(raw),
            "agent_id": agent_id,
            "raw_source": "endpoint_process_create",
            "sysmon_event_id": sysmon_id,
        }

    # --- Osquery process / process_events ---
    osquery = raw.get("osquery") or data.get("osquery")
    rows: List[Dict[str, Any]] = []
    if isinstance(osquery, list):
        rows = [r for r in osquery if isinstance(r, dict)]
    elif isinstance(osquery, dict):
        for key in ("results", "rows", "columns"):
            if isinstance(osquery.get(key), list):
                rows = [r for r in osquery[key] if isinstance(r, dict)]
                break
        if not rows and (osquery.get("pid") or osquery.get("path") or osquery.get("name")):
            rows = [osquery]
    # Wazuh osquery decoder sometimes flattens into data.*
    if not rows and (data.get("pid") or data.get("name")) and (
        "osquery" in groups or "osquery" in blob
    ):
        rows = [data]

    if rows:
        row = rows[0]
        path = _str_or_none(row.get("path") or row.get("name") or row.get("process_name"), 500)
        return {
            "pid": _int_or_none(row.get("pid")),
            "parent_pid": _int_or_none(row.get("parent") or row.get("parent_pid")),
            "process_guid": _str_or_none(row.get("upid") or row.get("process_guid"), 128),
            "parent_process_guid": _str_or_none(row.get("parent_upid"), 128),
            "process_name": path,
            "parent_process_name": _str_or_none(row.get("parent_path"), 500),
            "command_line": _str_or_none(row.get("cmdline") or row.get("command_line"), 4000),
            "parent_command_line": _str_or_none(row.get("parent_cmdline"), 4000),
            "username": _str_or_none(row.get("username") or row.get("user"), 255),
            "hash_md5": _str_or_none(row.get("md5"), 32),
            "hash_sha256": _str_or_none(row.get("sha256") or row.get("hash"), 64),
            "signed_status": _signed_status(path),
            "event_time": _parse_event_time(raw, row),
            "mitre_techniques": _mitre_tags(raw),
            "agent_id": agent_id,
            "raw_source": "endpoint_process_query",
        }

    # --- Auditd EXECVE / SYSCALL ---
    audit = data.get("audit") if isinstance(data.get("audit"), dict) else data
    if "audit" in groups or "auditd" in blob or audit.get("exe") or audit.get("pid"):
        exe = _str_or_none(audit.get("exe") or audit.get("comm"), 500)
        if exe or audit.get("pid"):
            cmdline = audit.get("command") or audit.get("cmd")
            if isinstance(audit.get("execve"), dict):
                parts = [
                    str(audit["execve"][k])
                    for k in sorted(audit["execve"].keys())
                    if str(k).startswith("a")
                ]
                if parts:
                    cmdline = " ".join(parts)
            return {
                "pid": _int_or_none(audit.get("pid")),
                "parent_pid": _int_or_none(audit.get("ppid")),
                "process_guid": None,
                "parent_process_guid": None,
                "process_name": exe,
                "parent_process_name": None,
                "command_line": _str_or_none(cmdline, 4000),
                "parent_command_line": None,
                "username": _str_or_none(audit.get("uid") or audit.get("auid"), 255),
                "hash_md5": None,
                "hash_sha256": None,
                "signed_status": _signed_status(exe),
                "event_time": _parse_event_time(raw, audit),
                "mitre_techniques": _mitre_tags(raw),
                "agent_id": agent_id,
                "raw_source": "endpoint_audit_exec",
            }

    return None


def _node_from_normalized(n: Dict[str, Any]) -> ProcessTreeNode:
    et = n.get("event_time")
    if isinstance(et, datetime):
        event_time = et.isoformat()
    elif et:
        event_time = str(et)
    else:
        event_time = None
    techniques = n.get("mitre_techniques") or []
    if isinstance(techniques, str):
        try:
            import json

            techniques = json.loads(techniques)
        except Exception:
            techniques = []
    if not isinstance(techniques, list):
        techniques = []
    return ProcessTreeNode(
        pid=n.get("pid"),
        parent_pid=n.get("parent_pid"),
        process_guid=n.get("process_guid"),
        parent_process_guid=n.get("parent_process_guid"),
        process_name=n.get("process_name"),
        parent_process_name=n.get("parent_process_name"),
        command_line=n.get("command_line"),
        parent_command_line=n.get("parent_command_line"),
        user=n.get("username") or n.get("user"),
        hash_md5=n.get("hash_md5"),
        hash_sha256=n.get("hash_sha256"),
        signed_status=n.get("signed_status"),
        mitre_techniques=[str(t) for t in techniques][:20],
        event_time=event_time,
        child_processes=[],
    )


def build_process_forest(
    raw_events: List[Dict[str, Any]],
    *,
    normalized_rows: Optional[List[Dict[str, Any]]] = None,
) -> ProcessTreeResponse:
    flat_norm: List[Dict[str, Any]] = list(normalized_rows or [])
    for raw in raw_events:
        if isinstance(raw, dict):
            n = normalize_process_event(raw)
            if n:
                flat_norm.append(n)

    if not flat_norm:
        return ProcessTreeResponse(
            root=None,
            events_considered=len(raw_events),
            message="No process-creation telemetry found for this incident.",
        )

    nodes = [_node_from_normalized(n) for n in flat_norm]

    # Index by ProcessGuid when present; else by pid.
    by_guid: Dict[str, ProcessTreeNode] = {}
    by_pid: Dict[int, ProcessTreeNode] = {}
    for node in nodes:
        if node.process_guid:
            by_guid[node.process_guid] = node
        if node.pid is not None:
            by_pid[node.pid] = node

    attached: set[int] = set()
    roots: List[ProcessTreeNode] = []

    for idx, node in enumerate(nodes):
        parent: Optional[ProcessTreeNode] = None
        if node.parent_process_guid and node.parent_process_guid in by_guid:
            parent = by_guid[node.parent_process_guid]
        elif node.parent_pid is not None and node.parent_pid in by_pid:
            # Timestamp-window fallback: parent should not start after child.
            candidate = by_pid[node.parent_pid]
            parent = candidate
        if parent is not None and parent is not node:
            parent.child_processes.append(node)
            attached.add(idx)
        else:
            roots.append(node)

    # Deduplicate roots that were also attached somehow
    root_nodes = [n for i, n in enumerate(nodes) if i not in attached] or roots
    if not root_nodes:
        root_nodes = roots or nodes[:1]

    root = (
        root_nodes[0]
        if len(root_nodes) == 1
        else ProcessTreeNode(
            process_name="(process tree)",
            child_processes=root_nodes,
        )
    )
    return ProcessTreeResponse(root=root, events_considered=len(raw_events) + len(normalized_rows or []))
