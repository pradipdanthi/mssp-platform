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
from app.services.list_pagination import clamp_pagination, pagination_meta
from app.services.soc_alert_taxonomy import (
    TAXONOMY_LABELS,
    TAXONOMY_SLUGS,
    TAXONOMY_TREE,
    enrich_alert_row,
    filter_by_asset_category,
    taxonomy_counts,
)

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
    tenant_status: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, max_length=200, description="Search name/code/contact"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    page, page_size, offset = clamp_pagination(page, page_size)
    where: list[str] = []
    params: list = []
    st = (tenant_status or "").strip().lower()
    if st in ("onboarding", "active", "inactive", "suspended"):
        where.append("t.status = %s")
        params.append(st)
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "t.name ILIKE %s OR "
            "t.short_code ILIKE %s OR "
            "COALESCE(t.primary_contact_name, '') ILIKE %s OR "
            "COALESCE(t.primary_contact_email, '') ILIKE %s OR "
            "COALESCE(t.country, '') ILIKE %s OR "
            "COALESCE(t.city, '') ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like, like, like, like])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    count_row = fetch_one(
        f"SELECT count(*)::int AS total FROM tenants t {where_sql};",
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)

    rows = fetch_all(
        f"""
        SELECT
            t.id::text,
            t.name,
            t.short_code,
            t.status,
            t.sla_level,
            t.business_criticality,
            t.timezone,
            t.deployment_mode,
            t.cloud_provider,
            t.primary_contact_name,
            t.primary_contact_email,
            t.primary_contact_phone,
            t.country,
            t.city,
            t.industry,
            t.contract_reference,
            t.licensed_endpoints,
            t.created_at,
            count(DISTINCT a.id) AS appliances,
            count(DISTINCT pa.id) AS protected_assets,
            count(DISTINCT i.id) AS incidents
        FROM tenants t
        LEFT JOIN appliances a ON a.tenant_id = t.id
        LEFT JOIN protected_assets pa ON pa.tenant_id = t.id
        LEFT JOIN incidents i ON i.tenant_id = t.id
        {where_sql}
        GROUP BY t.id
        ORDER BY t.created_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return {"tenants": rows, **pagination_meta(total, page, page_size)}


@router.get("/appliances")
def admin_appliances(
    appliance_status: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(
        default=None, max_length=200, description="Search name/site/tenant"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    page, page_size, offset = clamp_pagination(page, page_size)
    where: list[str] = []
    params: list = []
    st = (appliance_status or "").strip().lower()
    if st:
        where.append("a.status = %s")
        params.append(st)
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "a.appliance_name ILIKE %s OR "
            "a.site_name ILIKE %s OR "
            "t.name ILIKE %s OR "
            "t.short_code ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like, like])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    count_row = fetch_one(
        f"""
        SELECT count(*)::int AS total
        FROM appliances a
        JOIN tenants t ON t.id = a.tenant_id
        {where_sql};
        """,
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)

    rows = fetch_all(
        f"""
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
        {where_sql}
        ORDER BY a.last_seen_at DESC NULLS LAST
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return {"appliances": rows, **pagination_meta(total, page, page_size)}


@router.get("/alerts/taxonomy-summary")
def admin_alerts_taxonomy_summary(
    alert_status: Optional[
        Literal["new", "triaged", "incident_created", "false_positive", "closed"]
    ] = Query(default=None, alias="status"),
    severity: Optional[Literal["low", "medium", "high", "critical"]] = None,
    tenant_id: Optional[UUID] = None,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """KB-082: Category counts for alert filter badges (derived, no DB migration)."""
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
            sa.source_tool,
            sa.alert_title,
            sa.alert_description,
            sa.destination_host,
            sa.source_user,
            sa.raw_event
        FROM security_alerts sa
        {where_sql}
        ORDER BY sa.created_at DESC
        LIMIT 500;
        """,
        tuple(params),
    )
    enriched = [enrich_alert_row(r) for r in rows]
    return {
        "counts": taxonomy_counts(enriched),
        "tree": TAXONOMY_TREE,
        "labels": TAXONOMY_LABELS,
    }


@router.get("/alerts")
def admin_alerts(
    alert_status: Optional[
        Literal["new", "triaged", "incident_created", "false_positive", "closed"]
    ] = Query(default=None, alias="status"),
    severity: Optional[str] = Query(
        default=None,
        description="low|medium|high|critical or urgent/high_critical for high+critical",
    ),
    tenant_id: Optional[UUID] = None,
    asset_category: Optional[str] = Query(default=None, description="KB-082 taxonomy slug"),
    q: Optional[str] = Query(default=None, max_length=200, description="Search title/host/summary"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    if asset_category and asset_category not in TAXONOMY_SLUGS:
        asset_category = "uncategorized"
    page, page_size, offset = clamp_pagination(page, page_size)

    where = []
    params: list = []
    if alert_status is not None:
        where.append("sa.status = %s")
        params.append(alert_status)
    sev = (severity or "").strip().lower()
    if sev in ("urgent", "high_critical", "high,critical"):
        where.append("sa.severity IN ('high', 'critical')")
    elif sev in ("low", "medium", "high", "critical"):
        where.append("sa.severity = %s")
        params.append(sev)
    if tenant_id is not None:
        where.append("sa.tenant_id = %s")
        params.append(tenant_id)
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "sa.alert_title ILIKE %s OR "
            "COALESCE(sa.alert_description, '') ILIKE %s OR "
            "COALESCE(sa.destination_host, '') ILIKE %s OR "
            "COALESCE(sa.ai_plain_summary, '') ILIKE %s OR "
            "COALESCE(sa.external_alert_id, '') ILIKE %s OR "
            "t.name ILIKE %s OR "
            "t.short_code ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like, like, like, like, like])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    select_sql = f"""
        SELECT
            sa.id::text,
            t.name AS tenant_name,
            t.short_code,
            sa.external_alert_id,
            sa.source_tool,
            sa.severity,
            sa.alert_title,
            sa.alert_description,
            sa.source_ip::text,
            sa.destination_ip::text,
            sa.destination_host,
            sa.source_user,
            sa.raw_event,
            sa.ai_plain_summary,
            sa.ai_likely_attack_type,
            sa.ai_recommended_action,
            sa.customer_visible,
            sa.status,
            sa.created_at
        FROM security_alerts sa
        JOIN tenants t ON t.id = sa.tenant_id
        {where_sql}
        ORDER BY sa.created_at DESC
    """

    # Taxonomy category is derived in Python; when filtering by category we
    # page after enrichment. Otherwise use SQL LIMIT/OFFSET.
    if asset_category and asset_category != "all":
        rows = fetch_all(select_sql + " LIMIT 2000;", tuple(params))
        enriched = filter_by_asset_category(
            [enrich_alert_row(r) for r in rows], asset_category
        )
        total = len(enriched)
        page_rows = enriched[offset : offset + page_size]
        return {"alerts": page_rows, **pagination_meta(total, page, page_size)}

    count_row = fetch_one(
        f"""
        SELECT count(*)::int AS total
        FROM security_alerts sa
        JOIN tenants t ON t.id = sa.tenant_id
        {where_sql};
        """,
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)
    rows = fetch_all(
        select_sql + " LIMIT %s OFFSET %s;",
        tuple(params + [page_size, offset]),
    )
    enriched = [enrich_alert_row(r) for r in rows]
    return {"alerts": enriched, **pagination_meta(total, page, page_size)}


@router.get("/incidents")
def admin_incidents(
    incident_status: Optional[str] = Query(
        default=None,
        alias="status",
        description="Exact status, or open for open/in_progress/waiting_customer",
    ),
    severity: Optional[str] = Query(
        default=None,
        description="low|medium|high|critical or urgent/high_critical for high+critical",
    ),
    tenant_id: Optional[UUID] = None,
    q: Optional[str] = Query(
        default=None, max_length=200, description="Search number/title/tenant/summary"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    page, page_size, offset = clamp_pagination(page, page_size)
    where = []
    params: list = []
    st = (incident_status or "").strip().lower()
    if st == "open":
        where.append("i.status IN ('open', 'in_progress', 'waiting_customer')")
    elif st in ("in_progress", "waiting_customer", "resolved", "closed"):
        where.append("i.status = %s")
        params.append(st)
    sev = (severity or "").strip().lower()
    if sev in ("urgent", "high_critical", "high,critical"):
        where.append("i.severity IN ('high', 'critical')")
    elif sev in ("low", "medium", "high", "critical"):
        where.append("i.severity = %s")
        params.append(sev)
    if tenant_id is not None:
        where.append("i.tenant_id = %s")
        params.append(tenant_id)
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "i.incident_number ILIKE %s OR "
            "i.title ILIKE %s OR "
            "COALESCE(i.customer_visible_summary, '') ILIKE %s OR "
            "t.name ILIKE %s OR "
            "t.short_code ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like, like, like])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    count_row = fetch_one(
        f"""
        SELECT count(*)::int AS total
        FROM incidents i
        JOIN tenants t ON t.id = i.tenant_id
        {where_sql};
        """,
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)

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
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return {"incidents": rows, **pagination_meta(total, page, page_size)}


@router.get("/recommendations")
def admin_recommendations(
    rec_status: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(
        default=None, max_length=200, description="Search title/category/tenant"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """KB-062: cross-tenant recommendations list for Admin/SOC."""
    page, page_size, offset = clamp_pagination(page, page_size)
    where: list[str] = []
    params: list = []
    st = (rec_status or "").strip().lower()
    if st in ("open", "in_progress", "accepted_risk", "completed", "dismissed"):
        where.append("cr.status = %s")
        params.append(st)
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "cr.title ILIKE %s OR "
            "COALESCE(cr.category, '') ILIKE %s OR "
            "t.name ILIKE %s OR "
            "t.short_code ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like, like])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    count_row = fetch_one(
        f"""
        SELECT count(*)::int AS total
        FROM customer_recommendations cr
        JOIN tenants t ON t.id = cr.tenant_id
        {where_sql};
        """,
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)

    rows = fetch_all(
        f"""
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
        {where_sql}
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
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return {"recommendations": rows, **pagination_meta(total, page, page_size)}


@router.get("/notifications")
def admin_notifications(
    notif_status: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(
        default=None, max_length=200, description="Search type/preview/tenant"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """KB-062: cross-tenant notification events for Admin/SOC."""
    page, page_size, offset = clamp_pagination(page, page_size)
    where: list[str] = []
    params: list = []
    st = (notif_status or "").strip().lower()
    if st:
        where.append("ne.status = %s")
        params.append(st)
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "ne.notification_type ILIKE %s OR "
            "COALESCE(ne.message_body, '') ILIKE %s OR "
            "COALESCE(ne.provider, '') ILIKE %s OR "
            "t.name ILIKE %s OR "
            "t.short_code ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like, like, like])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    count_row = fetch_one(
        f"""
        SELECT count(*)::int AS total
        FROM notification_events ne
        JOIN tenants t ON t.id = ne.tenant_id
        {where_sql};
        """,
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)

    rows = fetch_all(
        f"""
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
        {where_sql}
        ORDER BY ne.created_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return {"notifications": rows, **pagination_meta(total, page, page_size)}

