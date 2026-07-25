"""
KB-012: Admin/SOC endpoints, moved out of app/main.py during route
modularization. Behavior is unchanged from the original main.py versions -
same paths, same SQL, same response shapes - only the file/router they live
in changed.

KB-011 auth/RBAC behavior is preserved unchanged: every endpoint below
requires Depends(require_roles(*ADMIN_SOC_ROLES)), so only platform_admin,
soc_manager, and soc_analyst may call them (401 with no/invalid token, 403
for a valid token with a different role, e.g. customer_admin/customer_viewer).
"""

from typing import Any, Dict, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import require_roles
from app.db.session import fetch_all, fetch_one

router = APIRouter(prefix="/admin", tags=["admin"])

# KB-011: roles allowed on every /admin/* endpoint and allowed cross-tenant
# read access on /customer/* endpoints (for support/troubleshooting).
# Customer roles (customer_admin, customer_viewer) are never in this tuple,
# so they are rejected with 403 on /admin/* automatically.
ADMIN_SOC_ROLES = ("platform_admin", "soc_manager", "soc_analyst")


@router.get("/dashboard")
def admin_dashboard(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    overview = fetch_one(
        """
        SELECT
            (SELECT count(*) FROM tenants) AS total_tenants,
            (SELECT count(*) FROM tenants WHERE status = 'active') AS active_tenants,
            (SELECT count(*) FROM appliances) AS total_appliances,
            (SELECT count(*) FROM appliances WHERE status = 'online') AS online_appliances,
            (SELECT count(*) FROM appliances WHERE status = 'offline') AS offline_appliances,
            (SELECT count(*) FROM protected_assets) AS protected_assets,
            (SELECT count(*) FROM security_alerts) AS total_alerts,
            (SELECT count(*) FROM security_alerts WHERE severity IN ('high','critical')) AS high_or_critical_alerts,
            (SELECT count(*) FROM security_alerts WHERE status = 'new') AS new_alerts,
            (SELECT count(*) FROM incidents) AS total_incidents,
            (SELECT count(*) FROM incidents WHERE status IN ('open','in_progress','waiting_customer')) AS open_incidents,
            (SELECT count(*) FROM customer_recommendations WHERE status = 'open') AS open_recommendations,
            (SELECT count(*) FROM notification_events WHERE status IN ('sent','delivered','acknowledged')) AS notifications_sent
        ;
        """
    )

    severity_breakdown = fetch_all(
        """
        SELECT severity, count(*) AS count
        FROM security_alerts
        GROUP BY severity
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 4
                ELSE 5
            END;
        """
    )

    tenant_risk = fetch_all(
        """
        SELECT
            t.name,
            t.short_code,
            t.sla_level,
            t.business_criticality,
            count(DISTINCT a.id) AS appliances,
            count(DISTINCT CASE WHEN a.status = 'online' THEN a.id END) AS online_appliances,
            count(DISTINCT sa.id) AS alerts,
            count(DISTINCT CASE WHEN sa.severity IN ('high','critical') THEN sa.id END) AS high_or_critical_alerts,
            count(DISTINCT i.id) AS incidents,
            count(DISTINCT CASE WHEN i.status IN ('open','in_progress','waiting_customer') THEN i.id END) AS open_incidents
        FROM tenants t
        LEFT JOIN appliances a ON a.tenant_id = t.id
        LEFT JOIN security_alerts sa ON sa.tenant_id = t.id
        LEFT JOIN incidents i ON i.tenant_id = t.id
        GROUP BY t.name, t.short_code, t.sla_level, t.business_criticality
        ORDER BY high_or_critical_alerts DESC, open_incidents DESC, t.name;
        """
    )

    return {
        "overview": overview,
        "severity_breakdown": severity_breakdown,
        "tenant_risk_summary": tenant_risk,
    }


@router.get("/tenants")
def admin_tenants(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
            t.id::text,
            t.name,
            t.short_code,
            t.status,
            t.sla_level,
            t.business_criticality,
            t.timezone,
            t.created_at,
            count(DISTINCT a.id) AS appliances,
            count(DISTINCT pa.id) AS protected_assets,
            count(DISTINCT i.id) AS incidents
        FROM tenants t
        LEFT JOIN appliances a ON a.tenant_id = t.id
        LEFT JOIN protected_assets pa ON pa.tenant_id = t.id
        LEFT JOIN incidents i ON i.tenant_id = t.id
        GROUP BY t.id
        ORDER BY t.created_at DESC;
        """
    )
    return {"tenants": rows}


@router.get("/appliances")
def admin_appliances(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
            t.name AS tenant_name,
            t.short_code,
            a.id::text,
            a.appliance_name,
            a.site_name,
            a.status,
            a.agent_version,
            a.config_version,
            a.update_status,
            a.local_ip::text,
            a.last_source_ip::text,
            a.last_seen_at,
            h.health_status,
            h.cpu_percent,
            h.memory_percent,
            h.disk_percent,
            h.heartbeat_at
        FROM appliances a
        JOIN tenants t ON t.id = a.tenant_id
        LEFT JOIN LATERAL (
            SELECT *
            FROM appliance_heartbeats h
            WHERE h.appliance_id = a.id
            ORDER BY h.heartbeat_at DESC
            LIMIT 1
        ) h ON true
        ORDER BY a.last_seen_at DESC NULLS LAST;
        """
    )
    return {"appliances": rows}


@router.get("/alerts")
def admin_alerts(
    alert_status: Optional[
        Literal["new", "triaged", "incident_created", "false_positive", "closed"]
    ] = Query(default=None, alias="status"),
    severity: Optional[Literal["low", "medium", "high", "critical"]] = None,
    tenant_id: Optional[UUID] = None,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    where = []
    params = []
    if alert_status is not None:
        where.append("sa.status = %s")
        params.append(alert_status)
    if severity is not None:
        where.append("sa.severity = %s")
        params.append(severity)
    if tenant_id is not None:
        where.append("sa.tenant_id = %s")
        params.append(tenant_id)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    rows = fetch_all(
        f"""
        SELECT
            sa.id::text,
            t.name AS tenant_name,
            t.short_code,
            sa.external_alert_id,
            sa.source_tool,
            sa.severity,
            sa.alert_title,
            sa.source_ip::text,
            sa.destination_ip::text,
            sa.destination_host,
            sa.ai_plain_summary,
            sa.ai_likely_attack_type,
            sa.customer_visible,
            sa.status,
            sa.created_at
        FROM security_alerts sa
        JOIN tenants t ON t.id = sa.tenant_id
        {where_sql}
        ORDER BY sa.created_at DESC
        LIMIT 100;
        """,
        tuple(params),
    )
    return {"alerts": rows}


@router.get("/incidents")
def admin_incidents(
    incident_status: Optional[
        Literal["open", "in_progress", "waiting_customer", "resolved", "closed"]
    ] = Query(default=None, alias="status"),
    severity: Optional[Literal["low", "medium", "high", "critical"]] = None,
    tenant_id: Optional[UUID] = None,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    where = []
    params = []
    if incident_status is not None:
        where.append("i.status = %s")
        params.append(incident_status)
    if severity is not None:
        where.append("i.severity = %s")
        params.append(severity)
    if tenant_id is not None:
        where.append("i.tenant_id = %s")
        params.append(tenant_id)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    rows = fetch_all(
        f"""
        SELECT
            i.id::text,
            t.name AS tenant_name,
            t.short_code,
            i.incident_number,
            i.title,
            i.severity,
            i.status,
            u.full_name AS assigned_to,
            i.customer_visible_summary,
            i.customer_action_required,
            i.opened_at,
            i.created_at
        FROM incidents i
        JOIN tenants t ON t.id = i.tenant_id
        LEFT JOIN platform_users u ON u.id = i.assigned_to_user_id
        {where_sql}
        ORDER BY i.created_at DESC
        LIMIT 100;
        """,
        tuple(params),
    )
    return {"incidents": rows}


@router.get("/recommendations")
def admin_recommendations(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """KB-062: cross-tenant recommendations list for Admin/SOC (latest 100)."""
    rows = fetch_all(
        """
        SELECT
            cr.id::text,
            t.name AS tenant_name,
            t.short_code,
            cr.title,
            cr.priority,
            cr.category,
            cr.status,
            cr.customer_visible,
            cr.due_at,
            cr.completed_at,
            cr.created_at
        FROM customer_recommendations cr
        JOIN tenants t ON t.id = cr.tenant_id
        ORDER BY
            CASE cr.status
                WHEN 'open' THEN 1
                WHEN 'in_progress' THEN 2
                ELSE 3
            END,
            CASE cr.priority
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 4
                ELSE 5
            END,
            cr.created_at DESC
        LIMIT 100;
        """
    )
    return {"recommendations": rows}


@router.get("/notifications")
def admin_notifications(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """KB-062: cross-tenant notification events for Admin/SOC (latest 100)."""
    rows = fetch_all(
        """
        SELECT
            ne.id::text,
            t.name AS tenant_name,
            t.short_code,
            ne.notification_type,
            ne.status,
            ne.provider,
            left(ne.message_body, 240) AS message_preview,
            ne.sent_at,
            ne.delivered_at,
            ne.created_at
        FROM notification_events ne
        JOIN tenants t ON t.id = ne.tenant_id
        ORDER BY ne.created_at DESC
        LIMIT 100;
        """
    )
    return {"notifications": rows}

