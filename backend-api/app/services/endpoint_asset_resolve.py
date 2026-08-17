"""Link enrolled endpoints to alerts so isolate works for every new customer/agent.

Appliance alerts are privacy-scrubbed (no raw Wazuh agent block). Heartbeat inventory
already stores hostname + wazuh_agent_id on protected_assets. This module is the
durable join used at ingest and at isolate time so operators never re-map by hand.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence

_AGENT_EQ_RE = re.compile(r"\bagent=([^\s;]+)", re.I)


def hostname_candidates(*values: Optional[str]) -> list[str]:
    """Exact hostnames plus short names (before the first dot), plus agent= from text."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = (raw or "").strip()
        if not text:
            continue
        match = _AGENT_EQ_RE.search(text)
        token = (match.group(1).strip() if match else text)
        for variant in (token, token.split(".", 1)[0]):
            key = variant.lower()
            if variant and key not in seen:
                seen.add(key)
                out.append(variant)
    return out


def agent_stub_raw_event(linked: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """SOC-only stub so EDR UI can read agent.id without a raw engine payload."""
    if not linked:
        return {}
    agent: Dict[str, Any] = {}
    if linked.get("wazuh_agent_id"):
        agent["id"] = linked["wazuh_agent_id"]
    if linked.get("hostname"):
        agent["name"] = linked["hostname"]
    if linked.get("ip"):
        agent["ip"] = linked["ip"]
    return {"agent": agent, "mssp": {"linked_from": "endpoint_inventory"}} if agent else {}


def resolve_endpoint_asset(
    tenant_id: str,
    *,
    wazuh_agent_id: Optional[str] = None,
    hostname: Optional[str] = None,
    alert_description: Optional[str] = None,
    cur: Any = None,
) -> Optional[Dict[str, Optional[str]]]:
    """Return enrolled asset {id, hostname, wazuh_agent_id, os_name, ip} or None."""
    agent_id = (wazuh_agent_id or "").strip()
    if agent_id:
        row = _fetch(
            cur,
            """
            SELECT
                id::text AS id,
                hostname,
                os_name,
                CASE WHEN ip_address IS NOT NULL THEN host(ip_address) ELSE NULL END AS ip,
                details->>'wazuh_agent_id' AS wazuh_agent_id
            FROM protected_assets
            WHERE tenant_id = %s::uuid
              AND details->>'wazuh_agent_id' = %s
            ORDER BY updated_at DESC NULLS LAST, created_at DESC
            LIMIT 1;
            """,
            (tenant_id, agent_id),
        )
        mapped = _row_to_asset(row)
        if mapped:
            return mapped

    hosts = hostname_candidates(hostname, alert_description)
    if not hosts:
        return None
    lowered = [h.lower() for h in hosts]
    row = _fetch(
        cur,
        """
        SELECT
            id::text AS id,
            hostname,
            os_name,
            CASE WHEN ip_address IS NOT NULL THEN host(ip_address) ELSE NULL END AS ip,
            details->>'wazuh_agent_id' AS wazuh_agent_id
        FROM protected_assets
        WHERE tenant_id = %s::uuid
          AND coalesce(details->>'wazuh_agent_id', '') <> ''
          AND (
                lower(hostname) = ANY(%s)
             OR lower(split_part(hostname, '.', 1)) = ANY(%s)
          )
        ORDER BY updated_at DESC NULLS LAST, created_at DESC
        LIMIT 1;
        """,
        (tenant_id, lowered, lowered),
    )
    return _row_to_asset(row)


def _row_to_asset(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Optional[str]]]:
    if not row:
        return None
    wazuh_id = str(row.get("wazuh_agent_id") or "").strip() or None
    if not wazuh_id:
        return None
    return {
        "id": str(row.get("id") or "").strip() or None,
        "hostname": (row.get("hostname") or None),
        "os_name": (row.get("os_name") or None),
        "ip": (row.get("ip") or None),
        "wazuh_agent_id": wazuh_id,
    }


def _fetch(cur: Any, sql: str, params: Sequence[Any]) -> Optional[Dict[str, Any]]:
    if cur is not None:
        cur.execute(sql, params)
        return cur.fetchone()
    from app.db.session import fetch_one

    return fetch_one(sql, tuple(params))
