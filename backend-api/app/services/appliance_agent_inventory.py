"""Upsert protected_assets from appliance-reported local Wazuh agent inventory."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.db.session import fetch_one, fetch_one_write
from app.services.agent_asset_sync import _map_asset_type, _map_status

logger = logging.getLogger(__name__)


def sync_appliance_agent_inventory(
    *,
    tenant_id: str,
    appliance_id: str,
    agents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Sync agents reported by an on-prem appliance Manager into protected_assets.

    Each agent dict may include: id, name, status, ip, os_name, os_platform, last_keep_alive.
    """
    if not agents:
        return {"synced": 0, "created": 0, "updated": 0, "error": None}

    created = 0
    updated = 0
    for agent in agents:
        agent_id = str(agent.get("id") or "").strip()
        if not agent_id:
            continue
        hostname = (agent.get("name") or f"agent-{agent_id}").strip()
        os_name = agent.get("os_name")
        status_raw = agent.get("status")
        status = _map_status(status_raw if isinstance(status_raw, str) else None)
        asset_type = _map_asset_type(os_name, agent.get("os_platform"))
        last_seen = agent.get("last_keep_alive")
        ip_addr = agent.get("ip")
        details = {
            "source": "appliance_local_manager",
            "wazuh_agent_id": agent_id,
            "appliance_id": appliance_id,
            "enrollment_status": status_raw,
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
            existing = fetch_one(
                """
                SELECT id::text
                FROM protected_assets
                WHERE tenant_id = %s::uuid
                  AND appliance_id = %s::uuid
                  AND lower(coalesce(hostname, '')) = lower(%s)
                LIMIT 1;
                """,
                (tenant_id, appliance_id, hostname),
            )

        safe_ip = ip_addr if ip_addr and ip_addr not in ("any", "0.0.0.0", "127.0.0.1") else None

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
                    appliance_id = %s::uuid,
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
                    safe_ip,
                    appliance_id,
                    json.dumps(details),
                    existing["id"],
                ),
            )
            updated += 1
        else:
            fetch_one_write(
                """
                INSERT INTO protected_assets (
                    tenant_id, appliance_id, hostname, ip_address, asset_type, os_name,
                    criticality, status, last_seen_at, details
                )
                VALUES (
                    %s::uuid, %s::uuid, %s, %s::inet, %s, %s,
                    'medium', %s, %s::timestamptz, %s::jsonb
                )
                RETURNING id::text;
                """,
                (
                    tenant_id,
                    appliance_id,
                    hostname,
                    safe_ip,
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
        "appliance_id": appliance_id,
        "error": None,
    }
