"""Sync enrolled endpoint agents into protected_assets for portal Assets views."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.db.session import fetch_one, fetch_one_write
from app.services import wazuh_client
from app.services.tenant_engine_provisioner import get_binding, wazuh_group_for

logger = logging.getLogger(__name__)


def _map_status(raw: Optional[str]) -> str:
    key = (raw or "").strip().lower()
    if key == "active":
        return "active"
    if key in ("disconnected", "never_connected"):
        return "inactive"
    return "unknown"


def _map_asset_type(os_name: Optional[str], os_platform: Optional[str]) -> str:
    blob = f"{os_name or ''} {os_platform or ''}".lower()
    if "windows" in blob and "server" not in blob:
        return "workstation"
    if "windows" in blob or "linux" in blob or "ubuntu" in blob or "centos" in blob:
        return "server"
    return "other"


def sync_tenant_endpoint_agents(tenant_id: str, *, short_code: Optional[str] = None) -> Dict[str, Any]:
    """
    Upsert protected_assets rows for agents in this tenant's Wazuh group.

    Idempotent via details.wazuh_agent_id. Failures are logged and returned;
    callers may still serve existing DB rows.
    """
    binding = get_binding(tenant_id)
    group = (binding or {}).get("wazuh_agent_group")
    if not group:
        if not short_code:
            tenant = fetch_one("SELECT short_code FROM tenants WHERE id = %s::uuid;", (tenant_id,))
            short_code = (tenant or {}).get("short_code")
        if not short_code:
            return {"synced": 0, "created": 0, "updated": 0, "error": "no_group"}
        group = wazuh_group_for(short_code)

    try:
        agents = wazuh_client.list_agents_in_group(group)
    except Exception as exc:  # noqa: BLE001 — keep Assets page available
        logger.warning("endpoint agent sync failed for tenant %s: %s", tenant_id, exc)
        return {"synced": 0, "created": 0, "updated": 0, "error": str(exc)[:200]}

    created = 0
    updated = 0
    for agent in agents:
        agent_id = str(agent.get("id") or "").strip()
        hostname = (agent.get("name") or f"agent-{agent_id}").strip()
        os_name = agent.get("os_name")
        status = _map_status(agent.get("status") if isinstance(agent.get("status"), str) else None)
        asset_type = _map_asset_type(os_name, agent.get("os_platform"))
        last_seen = agent.get("last_keep_alive")
        ip_addr = agent.get("ip")
        # Skip placeholder / never-connected manager-like IPs only if no name.
        details = {
            "source": "endpoint_agent",
            "wazuh_agent_id": agent_id,
            "wazuh_agent_group": group,
            "enrollment_status": agent.get("status"),
        }

        existing = fetch_one(
            """
            SELECT id::text
            FROM protected_assets
            WHERE tenant_id = %s::uuid
              AND details->>'wazuh_agent_id' = %s
            LIMIT 1;
            """,
            (tenant_id, agent_id),
        )
        if not existing:
            # Fallback: same hostname already tracked for this tenant.
            existing = fetch_one(
                """
                SELECT id::text
                FROM protected_assets
                WHERE tenant_id = %s::uuid
                  AND lower(coalesce(hostname, '')) = lower(%s)
                LIMIT 1;
                """,
                (tenant_id, hostname),
            )

        if existing:
            fetch_one_write(
                """
                UPDATE protected_assets
                SET
                    hostname = %s,
                    os_name = COALESCE(%s, os_name),
                    asset_type = %s,
                    status = %s,
                    last_seen_at = COALESCE(%s::timestamptz, last_seen_at),
                    ip_address = COALESCE(%s::inet, ip_address),
                    details = COALESCE(details, '{}'::jsonb) || %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s::uuid
                RETURNING id::text;
                """,
                (
                    hostname,
                    os_name,
                    asset_type,
                    status,
                    last_seen,
                    ip_addr if ip_addr and ip_addr not in ("any", "0.0.0.0") else None,
                    json.dumps(details),
                    existing["id"],
                ),
            )
            updated += 1
        else:
            fetch_one_write(
                """
                INSERT INTO protected_assets (
                    tenant_id, hostname, ip_address, asset_type, os_name,
                    criticality, status, last_seen_at, details
                )
                VALUES (
                    %s::uuid, %s, %s::inet, %s, %s,
                    'medium', %s, %s::timestamptz, %s::jsonb
                )
                RETURNING id::text;
                """,
                (
                    tenant_id,
                    hostname,
                    ip_addr if ip_addr and ip_addr not in ("any", "0.0.0.0") else None,
                    asset_type,
                    os_name,
                    status,
                    last_seen,
                    json.dumps(details),
                ),
            )
            created += 1

    return {
        "synced": len(agents),
        "created": created,
        "updated": updated,
        "group": group,
        "error": None,
    }
