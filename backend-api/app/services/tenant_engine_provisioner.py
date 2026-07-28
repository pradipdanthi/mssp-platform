"""Provision Wazuh agent groups + TheHive org/tag mappings for tenants."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.db.session import fetch_all, fetch_one, fetch_one_write
from app.services import thehive_client, wazuh_client
from app.services.audit_service import write_audit_event

logger = logging.getLogger(__name__)


def wazuh_group_for(short_code: str) -> str:
    code = re.sub(r"[^A-Za-z0-9_]", "_", short_code.strip().upper())
    return f"tenant_{code}"


def thehive_org_for(short_code: str) -> str:
    code = re.sub(r"[^A-Za-z0-9_-]", "-", short_code.strip().upper())
    return f"MSSP-{code}"


def thehive_tag_for(short_code: str) -> str:
    code = short_code.strip().upper()
    return f"tenant:{code}"


def get_binding(tenant_id: str) -> Dict[str, Any]:
    return (
        fetch_one(
            """
            SELECT
                tenant_id::text,
                wazuh_agent_group,
                wazuh_group_status,
                wazuh_last_error,
                wazuh_provisioned_at::text,
                thehive_org_name,
                thehive_tenant_tag,
                thehive_org_status,
                thehive_last_error,
                thehive_provisioned_at::text,
                last_provision_attempt_at::text,
                created_at::text,
                updated_at::text
            FROM tenant_engine_bindings
            WHERE tenant_id = %s::uuid;
            """,
            (tenant_id,),
        )
        or {}
    )


def ensure_binding_row(tenant_id: str, short_code: str) -> Dict[str, Any]:
    existing = get_binding(tenant_id)
    if existing:
        return existing
    return (
        fetch_one_write(
            """
            INSERT INTO tenant_engine_bindings (
                tenant_id, wazuh_agent_group, thehive_org_name, thehive_tenant_tag
            )
            VALUES (%s::uuid, %s, %s, %s)
            ON CONFLICT (tenant_id) DO UPDATE
              SET updated_at = NOW()
            RETURNING
                tenant_id::text,
                wazuh_agent_group,
                wazuh_group_status,
                wazuh_last_error,
                wazuh_provisioned_at::text,
                thehive_org_name,
                thehive_tenant_tag,
                thehive_org_status,
                thehive_last_error,
                thehive_provisioned_at::text,
                last_provision_attempt_at::text,
                created_at::text,
                updated_at::text;
            """,
            (
                tenant_id,
                wazuh_group_for(short_code),
                thehive_org_for(short_code),
                thehive_tag_for(short_code),
            ),
        )
        or {}
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def provision_tenant_engines(
    *,
    tenant_id: str,
    short_code: str,
    tenant_name: str,
    actor_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create/update engine bindings and attempt live Wazuh + TheHive provisioning.
    Tenant create always succeeds even if engines are unreachable — status reflects outcome.
    """
    binding = ensure_binding_row(tenant_id, short_code)
    group = binding.get("wazuh_agent_group") or wazuh_group_for(short_code)
    org_name = binding.get("thehive_org_name") or thehive_org_for(short_code)
    tag = binding.get("thehive_tenant_tag") or thehive_tag_for(short_code)

    wazuh_status = "skipped"
    wazuh_error: Optional[str] = None
    wazuh_at: Optional[str] = None
    thehive_status = "skipped"
    thehive_error: Optional[str] = None
    thehive_at: Optional[str] = None
    thehive_org_effective = org_name

    # --- Wazuh ---
    if not wazuh_client.credentials_configured():
        wazuh_status = "pending"
        wazuh_error = "Wazuh API credentials not configured on control plane"
    else:
        try:
            wazuh_client.ensure_agent_group(group)
            wazuh_status = "provisioned"
            wazuh_at = _now()
            wazuh_error = None
        except wazuh_client.WazuhClientError as exc:
            wazuh_status = "error"
            wazuh_error = str(exc)[:500]
            logger.warning("Wazuh provision failed tenant=%s: %s", short_code, wazuh_error)

    # --- TheHive ---
    if not thehive_client.credentials_configured():
        thehive_status = "pending"
        thehive_error = "TheHive password not configured on control plane"
    else:
        try:
            result = thehive_client.ensure_organisation(
                org_name, f"MSSP tenant {tenant_name} ({short_code})"
            )
            mode = result.get("mode")
            thehive_org_effective = str(result.get("org") or org_name)
            if mode == "provisioned":
                thehive_status = "provisioned"
            else:
                thehive_status = "tag_only"
                thehive_error = result.get("detail")
            thehive_at = _now()
        except thehive_client.TheHiveClientError as exc:
            thehive_status = "error"
            thehive_error = str(exc)[:500]
            logger.warning("TheHive provision failed tenant=%s: %s", short_code, thehive_error)

    updated = fetch_one_write(
        """
        UPDATE tenant_engine_bindings SET
            wazuh_agent_group = %s,
            wazuh_group_status = %s,
            wazuh_last_error = %s,
            wazuh_provisioned_at = CASE
                WHEN %s = 'provisioned' THEN COALESCE(wazuh_provisioned_at, NOW())
                ELSE wazuh_provisioned_at
            END,
            thehive_org_name = %s,
            thehive_tenant_tag = %s,
            thehive_org_status = %s,
            thehive_last_error = %s,
            thehive_provisioned_at = CASE
                WHEN %s IN ('provisioned', 'tag_only') THEN COALESCE(thehive_provisioned_at, NOW())
                ELSE thehive_provisioned_at
            END,
            last_provision_attempt_at = NOW(),
            updated_at = NOW()
        WHERE tenant_id = %s::uuid
        RETURNING
            tenant_id::text,
            wazuh_agent_group,
            wazuh_group_status,
            wazuh_last_error,
            wazuh_provisioned_at::text,
            thehive_org_name,
            thehive_tenant_tag,
            thehive_org_status,
            thehive_last_error,
            thehive_provisioned_at::text,
            last_provision_attempt_at::text,
            created_at::text,
            updated_at::text;
        """,
        (
            group,
            wazuh_status,
            wazuh_error,
            wazuh_status,
            thehive_org_effective,
            tag,
            thehive_status,
            thehive_error,
            thehive_status,
            tenant_id,
        ),
    )

    try:
        write_audit_event(
            action="tenant.engine_provision",
            entity_type="tenant",
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            entity_id=tenant_id,
            details={
                "short_code": short_code,
                "wazuh_agent_group": group,
                "wazuh_group_status": wazuh_status,
                "thehive_org_name": thehive_org_effective,
                "thehive_tenant_tag": tag,
                "thehive_org_status": thehive_status,
            },
        )
    except Exception:
        logger.exception("audit write failed for tenant engine provision")

    return updated or binding


def resolve_short_code_by_wazuh_group(group: str) -> Optional[str]:
    row = fetch_one(
        """
        SELECT t.short_code
        FROM tenant_engine_bindings b
        JOIN tenants t ON t.id = b.tenant_id
        WHERE b.wazuh_agent_group = %s
        LIMIT 1;
        """,
        (group,),
    )
    return row.get("short_code") if row else None


def resolve_short_code_by_thehive_tag(tag: str) -> Optional[str]:
    row = fetch_one(
        """
        SELECT t.short_code
        FROM tenant_engine_bindings b
        JOIN tenants t ON t.id = b.tenant_id
        WHERE b.thehive_tenant_tag = %s
        LIMIT 1;
        """,
        (tag,),
    )
    return row.get("short_code") if row else None


def backfill_all_tenants(actor_user_id: Optional[str] = None) -> Dict[str, Any]:
    tenants = fetch_all(
        "SELECT id::text AS id, short_code, name FROM tenants ORDER BY short_code;"
    )
    results = []
    for t in tenants:
        results.append(
            provision_tenant_engines(
                tenant_id=t["id"],
                short_code=t["short_code"],
                tenant_name=t["name"],
                actor_user_id=actor_user_id,
            )
        )
    return {"count": len(results), "bindings": results}
