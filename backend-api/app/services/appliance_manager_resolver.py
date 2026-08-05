"""Resolve Wazuh Manager address for agent packages (cloud vs appliance)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.db.session import fetch_one
from app.services.agent_package_builder import manager_address as cloud_manager_address

APPLIANCE_DEPLOYMENT_MODES = frozenset(
    {"cloud_appliance", "on_prem_appliance", "hybrid"}
)


def tenant_uses_appliance_manager(deployment_mode: Optional[str]) -> bool:
    return (deployment_mode or "").strip().lower() in APPLIANCE_DEPLOYMENT_MODES


def resolve_tenant_manager_address(tenant_id: str) -> Dict[str, Any]:
    """
    Return manager IP for endpoint agent packages.

    Appliance modes → primary online appliance local_ip (fallback last_source_ip).
    Cloud / on_prem_direct → control-plane Wazuh Manager env default.
    """
    tenant = fetch_one(
        """
        SELECT id::text, short_code, deployment_mode
        FROM tenants
        WHERE id = %s::uuid;
        """,
        (tenant_id,),
    )
    if not tenant:
        return {
            "manager_address": cloud_manager_address(),
            "source": "cloud_default",
            "appliance_id": None,
            "deployment_mode": None,
            "error": "tenant_not_found",
        }

    mode = (tenant.get("deployment_mode") or "cloud").strip().lower()
    if not tenant_uses_appliance_manager(mode):
        return {
            "manager_address": cloud_manager_address(),
            "source": "cloud_wazuh",
            "appliance_id": None,
            "deployment_mode": mode,
            "error": None,
        }

    appliance = fetch_one(
        """
        SELECT id::text,
               appliance_name,
               host(local_ip)::text AS local_ip,
               host(last_source_ip)::text AS last_source_ip,
               status
        FROM appliances
        WHERE tenant_id = %s::uuid
          AND status IN ('online', 'registered', 'maintenance')
        ORDER BY
            CASE status WHEN 'online' THEN 0 WHEN 'registered' THEN 1 ELSE 2 END,
            last_seen_at DESC NULLS LAST,
            created_at DESC
        LIMIT 1;
        """,
        (tenant_id,),
    )
    if not appliance:
        return {
            "manager_address": cloud_manager_address(),
            "source": "cloud_fallback_no_appliance",
            "appliance_id": None,
            "deployment_mode": mode,
            "error": "no_appliance_registered",
        }

    ip = (appliance.get("local_ip") or appliance.get("last_source_ip") or "").strip()
    if not ip:
        return {
            "manager_address": cloud_manager_address(),
            "source": "cloud_fallback_no_ip",
            "appliance_id": appliance["id"],
            "deployment_mode": mode,
            "error": "appliance_has_no_ip",
        }

    return {
        "manager_address": ip,
        "source": "appliance_local_manager",
        "appliance_id": appliance["id"],
        "appliance_name": appliance.get("appliance_name"),
        "deployment_mode": mode,
        "error": None,
    }


def primary_appliance_for_tenant(tenant_id: str) -> Optional[Dict[str, Any]]:
    return fetch_one(
        """
        SELECT id::text, tenant_id::text, appliance_name, status,
               host(local_ip)::text AS local_ip,
               enabled_services
        FROM appliances
        WHERE tenant_id = %s::uuid
          AND status IN ('online', 'registered', 'maintenance')
        ORDER BY
            CASE status WHEN 'online' THEN 0 WHEN 'registered' THEN 1 ELSE 2 END,
            last_seen_at DESC NULLS LAST
        LIMIT 1;
        """,
        (tenant_id,),
    )
