"""KB-083: Process tree from Sysmon Event ID 1 and Osquery process telemetry in raw_event."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas.edr import ProcessTreeNode, ProcessTreeResponse


def _int_or_none(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _node_from_sysmon(data: Dict[str, Any]) -> ProcessTreeNode:
    win = data.get("win") if isinstance(data.get("win"), dict) else data
    eventdata = win.get("eventdata") if isinstance(win.get("eventdata"), dict) else win
    return ProcessTreeNode(
        pid=_int_or_none(eventdata.get("ProcessId") or eventdata.get("process_id")),
        parent_pid=_int_or_none(eventdata.get("ParentProcessId") or eventdata.get("parent_process_id")),
        process_name=str(eventdata.get("Image") or eventdata.get("process_name") or "")[:500] or None,
        command_line=str(eventdata.get("CommandLine") or eventdata.get("command_line") or "")[:4000] or None,
        user=str(eventdata.get("User") or eventdata.get("user") or "")[:255] or None,
        hash_sha256=str(
            eventdata.get("Hashes") or eventdata.get("sha256") or eventdata.get("hash") or ""
        )[:128]
        or None,
        child_processes=[],
    )


def _node_from_osquery(row: Dict[str, Any]) -> ProcessTreeNode:
    return ProcessTreeNode(
        pid=_int_or_none(row.get("pid")),
        parent_pid=_int_or_none(row.get("parent")),
        process_name=str(row.get("name") or row.get("path") or "")[:500] or None,
        command_line=str(row.get("cmdline") or row.get("command_line") or "")[:4000] or None,
        user=str(row.get("username") or row.get("user") or "")[:255] or None,
        hash_sha256=str(row.get("sha256") or row.get("hash") or "")[:128] or None,
        child_processes=[],
    )


def _extract_process_nodes(raw: Dict[str, Any]) -> List[ProcessTreeNode]:
    nodes: List[ProcessTreeNode] = []
    rule = raw.get("rule") if isinstance(raw.get("rule"), dict) else {}
    groups = rule.get("groups") if isinstance(rule.get("groups"), list) else []
    is_sysmon = any("sysmon" in str(g).lower() for g in groups) or "sysmon" in str(raw).lower()
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw

    if is_sysmon or data.get("win") or data.get("eventdata"):
        nodes.append(_node_from_sysmon(data))

    osquery = raw.get("osquery") or data.get("osquery")
    if isinstance(osquery, list):
        for row in osquery:
            if isinstance(row, dict):
                nodes.append(_node_from_osquery(row))
    elif isinstance(osquery, dict):
        rows = osquery.get("results") or osquery.get("rows")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    nodes.append(_node_from_osquery(row))

    agent = raw.get("agent") if isinstance(raw.get("agent"), dict) else {}
    if not nodes and agent:
        nodes.append(
            ProcessTreeNode(
                process_name=str(agent.get("name") or "")[:255] or None,
                user=str(raw.get("syscheck") or "")[:1] or None,
                child_processes=[],
            )
        )
    return nodes


def build_process_forest(raw_events: List[Dict[str, Any]]) -> ProcessTreeResponse:
    flat: List[ProcessTreeNode] = []
    for raw in raw_events:
        if isinstance(raw, dict):
            flat.extend(_extract_process_nodes(raw))

    if not flat:
        return ProcessTreeResponse(
            root=None,
            events_considered=len(raw_events),
            message="No Sysmon or Osquery process telemetry found for this incident.",
        )

    by_pid: Dict[int, ProcessTreeNode] = {}
    for node in flat:
        if node.pid is not None:
            by_pid[node.pid] = node

    roots: List[ProcessTreeNode] = []
    for node in flat:
        if node.pid is None:
            roots.append(node)
            continue
        parent = node.parent_pid
        if parent is not None and parent in by_pid:
            by_pid[parent].child_processes.append(node)
        else:
            roots.append(node)

    root = roots[0] if len(roots) == 1 else ProcessTreeNode(
        process_name="(multiple roots)",
        child_processes=roots,
    )
    return ProcessTreeResponse(root=root, events_considered=len(raw_events))
