"""
KB-012: Customer-facing endpoints, moved out of app/main.py during route
modularization. Behavior is unchanged from the original main.py versions -
same paths, same SQL, same response shapes - only the file/router they live
in changed.

KB-011 auth/RBAC/tenant-isolation behavior is preserved unchanged: every
endpoint below requires Depends(get_current_user) plus a
require_tenant_match(...) call. platform_admin/soc_manager/soc_analyst keep
cross-tenant read access (for support/troubleshooting); customer_admin and
customer_viewer may only reach their own tenant's data, and a tenant
mismatch raises 404 (not 403) so a customer token can never be used to tell
"wrong tenant" apart from "tenant doesn't exist" (anti-enumeration).
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_current_user, require_tenant_match
from app.db.session import fetch_all, fetch_one

router = APIRouter(prefix="/customer", tags=["customer"])


@router.get("/dashboard/{short_code}")
def customer_dashboard(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = fetch_one(
        """
        SELECT id::text, name, short_code, status, sla_level, business_criticality, timezone
        FROM tenants
        WHERE short_code = %s;
        """,
        (short_code.upper(),),
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # KB-011: customer_admin/customer_viewer may only see their own tenant.
    # Raises 404 (not 403) on a tenant mismatch so a customer token can never
    # tell "wrong tenant" apart from "tenant doesn't exist". platform_admin,
    # soc_manager, and soc_analyst are exempt (cross-tenant support access).
    require_tenant_match(tenant["id"], current_user)

    tenant_id = tenant["id"]

    appliance_health = fetch_all(
        """
        SELECT
            a.appliance_name,
            a.site_name,
            a.status,
            a.last_seen_at,
            h.health_status,
            h.cpu_percent,
            h.memory_percent,
            h.disk_percent,
            h.heartbeat_at
        FROM appliances a
        LEFT JOIN LATERAL (
            SELECT *
            FROM appliance_heartbeats h
            WHERE h.appliance_id = a.id
            ORDER BY h.heartbeat_at DESC
            LIMIT 1
        ) h ON true
        WHERE a.tenant_id = %s
        ORDER BY a.site_name, a.appliance_name;
        """,
        (tenant_id,),
    )

    open_incidents = fetch_all(
        """
        SELECT
            incident_number,
            title,
            severity,
            status,
            customer_visible_summary,
            customer_action_required,
            opened_at
        FROM incidents
        WHERE tenant_id = %s
          AND status IN ('open','in_progress','waiting_customer')
        ORDER BY opened_at DESC;
        """,
        (tenant_id,),
    )

    recommendations = fetch_all(
        """
        SELECT
            title,
            description,
            priority,
            category,
            status,
            due_at
        FROM customer_recommendations
        WHERE tenant_id = %s
          AND customer_visible = true
        ORDER BY
            CASE priority
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 4
                ELSE 5
            END,
            created_at DESC;
        """,
        (tenant_id,),
    )

    monthly_reports = fetch_all(
        """
        SELECT report_month, status, executive_summary, metrics, published_at
        FROM monthly_reports
        WHERE tenant_id = %s
        ORDER BY report_month DESC
        LIMIT 12;
        """,
        (tenant_id,),
    )

    summary = fetch_one(
        """
        SELECT
            (SELECT count(*) FROM appliances WHERE tenant_id = %s) AS appliances,
            (SELECT count(*) FROM appliances WHERE tenant_id = %s AND status = 'online') AS online_appliances,
            (SELECT count(*) FROM incidents WHERE tenant_id = %s AND status IN ('open','in_progress','waiting_customer')) AS open_incidents,
            (SELECT count(*) FROM incidents WHERE tenant_id = %s AND severity IN ('high','critical') AND status IN ('open','in_progress','waiting_customer')) AS high_or_critical_open_incidents,
            (SELECT count(*) FROM customer_recommendations WHERE tenant_id = %s AND status = 'open' AND customer_visible = true) AS open_recommendations
        ;
        """,
        (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id),
    )

    return {
        "tenant": tenant,
        "security_summary": summary,
        "appliance_health": appliance_health,
        "open_incidents": open_incidents,
        "recommendations": recommendations,
        "monthly_reports": monthly_reports,
    }


@router.get("/incidents/{short_code}")
def customer_incidents(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # KB-011: see customer_dashboard() above for why this is 404, not 403.
    require_tenant_match(tenant["id"], current_user)

    rows = fetch_all(
        """
        SELECT
            incident_number,
            title,
            severity,
            status,
            customer_visible_summary,
            business_impact,
            customer_action_required,
            resolution_summary,
            opened_at,
            resolved_at,
            closed_at
        FROM incidents
        WHERE tenant_id = %s
        ORDER BY opened_at DESC;
        """,
        (tenant["id"],),
    )

    return {"tenant": tenant, "incidents": rows}


@router.get("/alerts/{short_code}")
def customer_alerts(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    KB-022: Tenant-scoped, customer-visible alerts only.

    Returns only customer-safe fields. Does not expose raw_event, IPs,
    external_alert_id, technical AI fields, MITRE mappings, or secrets.
    Filtered to customer_visible = true for the matched tenant.
    """
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # KB-011: see customer_dashboard() above for why this is 404, not 403.
    require_tenant_match(tenant["id"], current_user)

    rows = fetch_all(
        """
        SELECT
            id::text AS alert_id,
            alert_title AS title,
            severity,
            status,
            source_tool AS source,
            ai_plain_summary AS summary,
            alert_description AS description,
            event_time AS detected_at,
            destination_host AS hostname
        FROM security_alerts
        WHERE tenant_id = %s
          AND customer_visible = true
        ORDER BY event_time DESC NULLS LAST, created_at DESC
        LIMIT 100;
        """,
        (tenant["id"],),
    )

    return {"tenant": tenant, "alerts": rows}


@router.get("/assets/{short_code}")
def customer_assets(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    KB-023: Tenant-scoped customer appliance posture and protected assets.

    Returns only customer-safe fields. Does not expose API keys, key hints,
    activation tokens, hashes, IPs, health_snapshot/details JSON, or
    credential timestamps.
    """
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # KB-011: see customer_dashboard() above for why this is 404, not 403.
    require_tenant_match(tenant["id"], current_user)

    tenant_id = tenant["id"]

    appliances = fetch_all(
        """
        SELECT
            a.appliance_name,
            a.site_name,
            a.status,
            a.last_seen_at,
            h.health_status,
            h.cpu_percent,
            h.memory_percent,
            h.disk_percent,
            a.agent_version
        FROM appliances a
        LEFT JOIN LATERAL (
            SELECT
                health_status,
                cpu_percent,
                memory_percent,
                disk_percent
            FROM appliance_heartbeats h
            WHERE h.appliance_id = a.id
            ORDER BY h.heartbeat_at DESC
            LIMIT 1
        ) h ON true
        WHERE a.tenant_id = %s
        ORDER BY a.site_name, a.appliance_name
        LIMIT 200;
        """,
        (tenant_id,),
    )

    assets = fetch_all(
        """
        SELECT
            pa.id::text AS asset_id,
            pa.hostname,
            pa.asset_type,
            pa.criticality,
            pa.status,
            pa.os_name,
            pa.owner,
            pa.last_seen_at,
            a.appliance_name,
            a.site_name
        FROM protected_assets pa
        LEFT JOIN appliances a ON a.id = pa.appliance_id
        WHERE pa.tenant_id = %s
        ORDER BY
            CASE pa.criticality
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 4
                ELSE 5
            END,
            pa.hostname NULLS LAST,
            pa.created_at DESC
        LIMIT 200;
        """,
        (tenant_id,),
    )

    return {"tenant": tenant, "appliances": appliances, "assets": assets}
