"""SOC Console live activity feed — full MSSP stack pulse + in-memory AI ring.

No schema changes. Merges alerts, incidents, Secure Edge, appliance heartbeats,
notifications, audit, recommendations, and AI markers into one live stream.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.session import fetch_all
from app.services.soc_console_engines import resolve_lane

_LOCK = threading.Lock()
_RING: List[Dict[str, Any]] = []
_RING_MAX = 200


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def push_local_activity(
    *,
    kind: str,
    title: str,
    detail: str = "",
    severity: str = "info",
    alert_id: Optional[str] = None,
    incident_id: Optional[str] = None,
    actor: str = "soc_console",
) -> Dict[str, Any]:
    """Record an analyst/AI action into the live feed ring."""
    category = "agent" if kind.startswith("agent_") or kind.startswith("ai_") else "system"
    item = {
        "id": f"local-{uuid.uuid4().hex[:12]}",
        "kind": kind,
        "category": category,
        "lane": resolve_lane("soc_agent" if category == "agent" else "control_plane", category, kind),
        "title": title[:240],
        "detail": (detail or "")[:800],
        "severity": (severity or "info").lower(),
        "alert_id": alert_id,
        "incident_id": incident_id,
        "actor": actor[:120],
        "ts": _utc_now(),
        "source": "soc_console",
    }
    with _LOCK:
        _RING.insert(0, item)
        del _RING[_RING_MAX:]
    return item


def _local_since(since_iso: Optional[str]) -> List[Dict[str, Any]]:
    with _LOCK:
        items = list(_RING)
    if not since_iso:
        return items[:80]
    out = []
    for it in items:
        if str(it.get("ts") or "") > since_iso:
            out.append(it)
    return out


def _item(
    *,
    id: str,
    kind: str,
    category: str,
    title: str,
    detail: str,
    severity: str,
    ts: Optional[str],
    source: str,
    actor: str = "system",
    alert_id: Optional[str] = None,
    incident_id: Optional[str] = None,
    lane: Optional[str] = None,
    source_tool: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": id,
        "kind": kind,
        "category": category,
        "lane": lane or resolve_lane(source_tool or source, category, kind),
        "title": (title or "Event")[:240],
        "detail": (detail or "")[:800],
        "severity": (severity or "info").lower(),
        "alert_id": alert_id,
        "incident_id": incident_id,
        "actor": actor[:120],
        "ts": ts or _utc_now(),
        "source": source,
        "source_tool": source_tool,
    }


def _db_activity(limit: int = 80) -> List[Dict[str, Any]]:
    """Merge recent events across the MSSP control-plane data plane."""
    per = max(12, min(40, limit // 2))

    alerts = fetch_all(
        """
        SELECT id::text AS id, alert_title AS title, severity, status,
               destination_host, source_tool, ai_verdict,
               (created_at AT TIME ZONE 'utc')::text AS ts
        FROM security_alerts
        ORDER BY created_at DESC
        LIMIT %s;
        """,
        (per,),
    )
    incidents = fetch_all(
        """
        SELECT id::text AS id, incident_number, title, severity, status,
               (created_at AT TIME ZONE 'utc')::text AS ts
        FROM incidents
        ORDER BY created_at DESC
        LIMIT %s;
        """,
        (max(8, per // 2),),
    )
    edge = fetch_all(
        """
        SELECT id::text AS id, event_type, severity, summary, public_hostname,
               tenant_short_code,
               (created_at AT TIME ZONE 'utc')::text AS ts
        FROM secure_edge_events
        ORDER BY created_at DESC
        LIMIT %s;
        """,
        (max(8, per // 2),),
    )
    heartbeats = fetch_all(
        """
        SELECT DISTINCT ON (a.id)
               h.id::text AS id, a.appliance_name, a.status AS appliance_status,
               h.health_status, h.agent_version,
               (h.heartbeat_at AT TIME ZONE 'utc')::text AS ts
        FROM appliance_heartbeats h
        JOIN appliances a ON a.id = h.appliance_id
        ORDER BY a.id, h.heartbeat_at DESC
        LIMIT %s;
        """,
        (max(6, per // 3),),
    )
    notifications = fetch_all(
        """
        SELECT id::text AS id, notification_type, status, provider,
               left(message_body, 120) AS snippet,
               (created_at AT TIME ZONE 'utc')::text AS ts
        FROM notification_events
        ORDER BY created_at DESC
        LIMIT %s;
        """,
        (max(6, per // 3),),
    )
    audits = fetch_all(
        """
        SELECT id::text AS id, action, entity_type,
               (created_at AT TIME ZONE 'utc')::text AS ts
        FROM audit_logs
        ORDER BY created_at DESC
        LIMIT %s;
        """,
        (max(8, per // 2),),
    )
    recs = fetch_all(
        """
        SELECT id::text AS id, title, priority, status, category,
               (created_at AT TIME ZONE 'utc')::text AS ts
        FROM customer_recommendations
        ORDER BY created_at DESC
        LIMIT %s;
        """,
        (max(6, per // 3),),
    )
    ai_done = fetch_all(
        """
        SELECT id::text AS id, alert_title AS title, severity, ai_verdict, ai_confidence,
               (coalesce(ai_triaged_at, updated_at) AT TIME ZONE 'utc')::text AS ts
        FROM security_alerts
        WHERE ai_verdict IS NOT NULL
        ORDER BY coalesce(ai_triaged_at, updated_at) DESC
        LIMIT %s;
        """,
        (max(8, per // 2),),
    )

    items: List[Dict[str, Any]] = []

    for a in alerts or []:
        sev = (a.get("severity") or "info").lower()
        tool = a.get("source_tool")
        items.append(
            _item(
                id=f"alert-{a['id']}",
                kind="alert_new" if sev in ("critical", "high") else "alert",
                category="alert",
                title=a.get("title") or "Security alert",
                detail=(
                    f"host={a.get('destination_host') or '—'} status={a.get('status')} "
                    f"source={tool}"
                ),
                severity=sev,
                ts=a.get("ts"),
                source="security_alerts",
                actor="ingest",
                alert_id=a["id"],
                source_tool=tool,
            )
        )

    for i in incidents or []:
        items.append(
            _item(
                id=f"inc-{i['id']}",
                kind="incident",
                category="incident",
                title=f"{i.get('incident_number')}: {i.get('title')}",
                detail=f"status={i.get('status')}",
                severity=(i.get("severity") or "medium").lower(),
                ts=i.get("ts"),
                source="incidents",
                actor="soc",
                incident_id=i["id"],
            )
        )

    for e in edge or []:
        items.append(
            _item(
                id=f"edge-{e['id']}",
                kind="edge_event",
                category="edge",
                title=f"Edge {e.get('event_type') or 'event'}: {e.get('summary') or ''}",
                detail=(
                    f"host={e.get('public_hostname') or '—'} "
                    f"tenant={e.get('tenant_short_code') or '—'}"
                ),
                severity=(e.get("severity") or "info").lower(),
                ts=e.get("ts"),
                source="secure_edge_events",
                actor="secure_edge",
            )
        )

    for h in heartbeats or []:
        hs = (h.get("health_status") or "unknown").lower()
        sev = "critical" if hs == "critical" else ("medium" if hs == "warning" else "info")
        items.append(
            _item(
                id=f"hb-{h['id']}",
                kind="heartbeat",
                category="appliance",
                title=f"Appliance heartbeat · {h.get('appliance_name') or 'device'}",
                detail=(
                    f"health={hs} appliance={h.get('appliance_status')} "
                    f"agent={h.get('agent_version') or '—'}"
                ),
                severity=sev,
                ts=h.get("ts"),
                source="appliance_heartbeats",
                actor="appliance",
            )
        )

    for n in notifications or []:
        st = (n.get("status") or "queued").lower()
        sev = "high" if st == "failed" else "info"
        items.append(
            _item(
                id=f"notify-{n['id']}",
                kind="notification",
                category="notify",
                title=f"Notification {n.get('notification_type')} · {st}",
                detail=f"provider={n.get('provider') or '—'} · {n.get('snippet') or ''}",
                severity=sev,
                ts=n.get("ts"),
                source="notification_events",
                actor="notifier",
            )
        )

    for a in audits or []:
        items.append(
            _item(
                id=f"audit-{a['id']}",
                kind="audit",
                category="portal",
                title=f"Portal action · {a.get('action')}",
                detail=f"entity={a.get('entity_type')}",
                severity="info",
                ts=a.get("ts"),
                source="audit_logs",
                actor="portal",
            )
        )

    for r in recs or []:
        items.append(
            _item(
                id=f"rec-{r['id']}",
                kind="recommendation",
                category="customer",
                title=r.get("title") or "Recommendation",
                detail=f"priority={r.get('priority')} status={r.get('status')} cat={r.get('category')}",
                severity=(r.get("priority") or "medium").lower(),
                ts=r.get("ts"),
                source="customer_recommendations",
                actor="control_plane",
            )
        )

    for a in ai_done or []:
        items.append(
            _item(
                id=f"ai-{a['id']}-{str(a.get('ts') or '')[:19]}",
                kind="ai_triage",
                category="agent",
                title=f"AI triage · {a.get('ai_verdict') or 'verdict'}",
                detail=(
                    f"{a.get('title') or 'alert'} · confidence={a.get('ai_confidence') or '—'}"
                ),
                severity=(a.get("severity") or "info").lower(),
                ts=a.get("ts"),
                source="ai_triage",
                actor="soc_agent",
                alert_id=a["id"],
            )
        )

    items.sort(key=lambda x: str(x.get("ts") or ""), reverse=True)
    return items[:limit]


def list_activity(*, limit: int = 100) -> List[Dict[str, Any]]:
    merged = _local_since(None) + _db_activity(limit=limit)
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in sorted(merged, key=lambda x: str(x.get("ts") or ""), reverse=True):
        iid = it.get("id")
        if iid in seen:
            continue
        seen.add(iid)
        out.append(it)
        if len(out) >= limit:
            break
    return out


def poll_new_activity(*, since_iso: str, limit: int = 40) -> List[Dict[str, Any]]:
    """Return items newer than since_iso (lexicographic ISO compare)."""
    items = list_activity(limit=160)
    return [it for it in items if str(it.get("ts") or "") > since_iso][:limit]


def sleep_poll(seconds: float = 2.0) -> None:
    time.sleep(max(0.5, min(seconds, 10.0)))
