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

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_current_user, require_tenant_match
from app.db.session import fetch_all, fetch_one
from app.services.customer_safe_labels import customer_safe_alert_source
from app.services.list_pagination import clamp_pagination, pagination_meta
from app.services.soc_alert_taxonomy import enrich_alert_row

router = APIRouter(prefix="/customer", tags=["customer"])


def _customer_safe_alert_rows(rows: list) -> list:
    for row in rows:
        if "source" in row:
            row["source"] = customer_safe_alert_source(row.get("source"))
    return rows


def _customer_safe_alert_detail_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    enriched = enrich_alert_row(row)
    return {
        "alert_id": enriched.get("alert_id") or enriched.get("id"),
        "title": enriched.get("title") or enriched.get("alert_title"),
        "severity": enriched.get("severity"),
        "status": enriched.get("status"),
        "source": customer_safe_alert_source(enriched.get("source") or enriched.get("source_tool")),
        "summary": enriched.get("summary") or enriched.get("ai_plain_summary"),
        "description": enriched.get("description") or enriched.get("alert_description"),
        "detected_at": enriched.get("detected_at") or enriched.get("event_time"),
        "hostname": enriched.get("hostname") or enriched.get("destination_host"),
        "asset_category": enriched.get("asset_category"),
        "asset_category_label": enriched.get("asset_category_label"),
        "device_type": enriched.get("device_type"),
        "operating_system": enriched.get("display_operating_system"),
        "business_impact": enriched.get("ai_business_impact"),
        "recommended_action": enriched.get("ai_recommended_action"),
        "likely_attack_type": enriched.get("ai_likely_attack_type"),
        "criticality": enriched.get("asset_criticality"),
    }


def _customer_safe_incident_row(row: Dict[str, Any]) -> Dict[str, Any]:
    safe = dict(row)
    alert = _customer_safe_alert_detail_row(row)
    if alert:
        safe["hostname"] = alert.get("hostname")
        safe["asset_category"] = alert.get("asset_category")
        safe["asset_category_label"] = alert.get("asset_category_label")
        safe["device_type"] = alert.get("device_type")
        safe["operating_system"] = alert.get("operating_system")
        safe["recommended_action"] = alert.get("recommended_action")
        safe["likely_attack_type"] = alert.get("likely_attack_type")
        safe["criticality"] = alert.get("criticality")
    return safe


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
            i.incident_number,
            i.title,
            i.severity,
            i.status,
            i.customer_visible_summary,
            i.business_impact,
            i.customer_action_required,
            i.opened_at,
            sa.id::text AS alert_id,
            sa.alert_title AS alert_title,
            sa.source_tool AS source,
            sa.ai_plain_summary AS summary,
            sa.alert_description AS description,
            sa.event_time AS detected_at,
            sa.destination_host AS hostname,
            pa.hostname AS asset_hostname,
            pa.asset_type,
            pa.os_name AS asset_os_name,
            pa.criticality AS asset_criticality,
            sa.raw_event,
            sa.ai_recommended_action,
            sa.ai_likely_attack_type
        FROM incidents i
        LEFT JOIN security_alerts sa ON sa.id = i.primary_alert_id AND sa.customer_visible = true
        LEFT JOIN protected_assets pa ON pa.id = sa.asset_id
        WHERE i.tenant_id = %s
          AND i.status IN ('open','in_progress','waiting_customer')
        ORDER BY i.opened_at DESC;
        """,
        (tenant_id,),
    )
    open_incidents = [_customer_safe_incident_row(row) for row in open_incidents]

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
    status: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
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

    page, page_size, offset = clamp_pagination(page, page_size)
    where = ["i.tenant_id = %s"]
    params: list = [tenant["id"]]
    st = (status or "").strip().lower()
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
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "i.incident_number ILIKE %s OR "
            "i.title ILIKE %s OR "
            "COALESCE(i.customer_visible_summary, '') ILIKE %s OR "
            "COALESCE(sa.destination_host, '') ILIKE %s OR "
            "COALESCE(pa.hostname, '') ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like, like, like])
    where_sql = " AND ".join(where)

    count_row = fetch_one(
        f"""
        SELECT count(*)::int AS total
        FROM incidents i
        LEFT JOIN security_alerts sa ON sa.id = i.primary_alert_id AND sa.customer_visible = true
        LEFT JOIN protected_assets pa ON pa.id = sa.asset_id
        WHERE {where_sql};
        """,
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)

    rows = fetch_all(
        f"""
        SELECT
            i.incident_number,
            i.title,
            i.severity,
            i.status,
            i.customer_visible_summary,
            i.business_impact,
            i.customer_action_required,
            i.resolution_summary,
            i.opened_at,
            i.resolved_at,
            i.closed_at,
            sa.id::text AS alert_id,
            sa.alert_title AS alert_title,
            sa.source_tool AS source,
            sa.ai_plain_summary AS summary,
            sa.alert_description AS description,
            sa.event_time AS detected_at,
            sa.destination_host AS hostname,
            pa.hostname AS asset_hostname,
            pa.asset_type,
            pa.os_name AS asset_os_name,
            pa.criticality AS asset_criticality,
            sa.raw_event,
            sa.ai_recommended_action,
            sa.ai_likely_attack_type
        FROM incidents i
        LEFT JOIN security_alerts sa ON sa.id = i.primary_alert_id AND sa.customer_visible = true
        LEFT JOIN protected_assets pa ON pa.id = sa.asset_id
        WHERE {where_sql}
        ORDER BY i.opened_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )

    return {
        "tenant": tenant,
        "incidents": [_customer_safe_incident_row(row) for row in rows],
        **pagination_meta(total, page, page_size),
    }


@router.get("/incidents/{short_code}/{incident_number}")
def customer_incident_detail(
    short_code: str,
    incident_number: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    KB-025: Tenant-scoped, read-only customer incident detail.

    Looks up by incident_number (not internal UUID). Returns only customer-safe
    incident fields, customer-visible timeline rows, and related alerts that are
    customer_visible for the same tenant. Omits comments, internal notes,
    assignment, and all secrets/raw internals.
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

    incident = fetch_one(
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
          AND incident_number = %s;
        """,
        (tenant_id, incident_number),
    )

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Schema has visibility IN ('internal','customer') — only customer rows.
    timeline = fetch_all(
        """
        SELECT
            event_type,
            title,
            created_at
        FROM incident_timeline
        WHERE incident_id = (
            SELECT id FROM incidents
            WHERE tenant_id = %s AND incident_number = %s
        )
          AND visibility = 'customer'
        ORDER BY created_at ASC;
        """,
        (tenant_id, incident_number),
    )

    # Related alerts via incident_alerts; same tenant + customer_visible only.
    related_alerts = fetch_all(
        """
        SELECT
            sa.id::text AS alert_id,
            sa.alert_title AS title,
            sa.severity,
            sa.status,
            sa.source_tool AS source,
            sa.ai_plain_summary AS summary,
            sa.alert_description AS description,
            sa.event_time AS detected_at,
            sa.destination_host AS hostname,
            pa.hostname AS asset_hostname,
            pa.asset_type,
            pa.os_name AS asset_os_name,
            pa.criticality AS asset_criticality,
            sa.raw_event,
            sa.ai_business_impact,
            sa.ai_recommended_action,
            sa.ai_likely_attack_type
        FROM incident_alerts ia
        JOIN security_alerts sa ON sa.id = ia.alert_id
        JOIN incidents i ON i.id = ia.incident_id
        LEFT JOIN protected_assets pa ON pa.id = sa.asset_id
        WHERE i.tenant_id = %s
          AND i.incident_number = %s
          AND sa.tenant_id = %s
          AND sa.customer_visible = true
        ORDER BY sa.event_time DESC NULLS LAST, sa.created_at DESC;
        """,
        (tenant_id, incident_number, tenant_id),
    )
    related_alerts = [
        _customer_safe_alert_detail_row(row) for row in related_alerts
    ]

    primary_alert = fetch_one(
        """
        SELECT
            sa.id::text AS alert_id,
            sa.alert_title AS title,
            sa.severity,
            sa.status,
            sa.source_tool AS source,
            sa.ai_plain_summary AS summary,
            sa.alert_description AS description,
            sa.event_time AS detected_at,
            sa.destination_host AS hostname,
            pa.hostname AS asset_hostname,
            pa.asset_type,
            pa.os_name AS asset_os_name,
            pa.criticality AS asset_criticality,
            sa.raw_event,
            sa.ai_business_impact,
            sa.ai_recommended_action,
            sa.ai_likely_attack_type
        FROM incidents i
        JOIN security_alerts sa ON sa.id = i.primary_alert_id
        LEFT JOIN protected_assets pa ON pa.id = sa.asset_id
        WHERE i.tenant_id = %s
          AND i.incident_number = %s
          AND sa.customer_visible = true
        LIMIT 1;
        """,
        (tenant_id, incident_number),
    )

    return {
        "tenant": tenant,
        "incident": incident,
        "timeline": timeline,
        "related_alerts": related_alerts,
        "primary_alert": _customer_safe_alert_detail_row(primary_alert),
    }


@router.get("/alerts/{short_code}")
def customer_alerts(
    short_code: str,
    status: Optional[
        Literal["new", "triaged", "incident_created", "false_positive", "closed"]
    ] = None,
    severity: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
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

    page, page_size, offset = clamp_pagination(page, page_size)
    where = ["sa.tenant_id = %s", "sa.customer_visible = true"]
    params: list = [tenant["id"]]
    if status is not None:
        where.append("sa.status = %s")
        params.append(status)
    sev = (severity or "").strip().lower()
    if sev in ("urgent", "high_critical", "high,critical"):
        where.append("sa.severity IN ('high', 'critical')")
    elif sev in ("low", "medium", "high", "critical"):
        where.append("sa.severity = %s")
        params.append(sev)
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "sa.alert_title ILIKE %s OR "
            "COALESCE(sa.ai_plain_summary, '') ILIKE %s OR "
            "COALESCE(sa.destination_host, '') ILIKE %s OR "
            "COALESCE(pa.hostname, '') ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like, like])
    where_sql = " AND ".join(where)

    count_row = fetch_one(
        f"""
        SELECT count(*)::int AS total
        FROM security_alerts sa
        LEFT JOIN protected_assets pa ON pa.id = sa.asset_id
        WHERE {where_sql};
        """,
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)

    rows = fetch_all(
        f"""
        SELECT
            sa.id::text AS alert_id,
            sa.alert_title AS title,
            sa.severity,
            sa.status,
            sa.source_tool AS source,
            sa.ai_plain_summary AS summary,
            sa.alert_description AS description,
            sa.event_time AS detected_at,
            sa.destination_host AS hostname,
            pa.hostname AS asset_hostname,
            pa.asset_type,
            pa.os_name AS asset_os_name,
            pa.criticality AS asset_criticality,
            sa.raw_event,
            sa.ai_business_impact,
            sa.ai_recommended_action,
            sa.ai_likely_attack_type
        FROM security_alerts sa
        LEFT JOIN protected_assets pa ON pa.id = sa.asset_id
        WHERE {where_sql}
        ORDER BY sa.event_time DESC NULLS LAST, sa.created_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )

    return {
        "tenant": tenant,
        "alerts": [_customer_safe_alert_detail_row(row) for row in rows],
        **pagination_meta(total, page, page_size),
    }


@router.get("/alerts/{short_code}/{alert_id}")
def customer_alert_detail(
    short_code: str,
    alert_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    KB-029: Tenant-scoped, read-only customer alert detail.

    Looks up by alert_id (UUID). Returns only customer-safe fields.
    Filters customer_visible = true. Missing/hidden/wrong-tenant → 404.
    Does not expose raw_event, IPs, external_alert_id, technical AI, MITRE, or secrets.
    """
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # KB-011: see customer_dashboard() above for why this is 404, not 403.
    require_tenant_match(tenant["id"], current_user)

    alert = fetch_one(
        """
        SELECT
            sa.id::text AS alert_id,
            sa.alert_title AS title,
            sa.severity,
            sa.status,
            sa.source_tool AS source,
            sa.ai_plain_summary AS summary,
            sa.alert_description AS description,
            sa.event_time AS detected_at,
            sa.destination_host AS hostname,
            pa.hostname AS asset_hostname,
            pa.asset_type,
            pa.os_name AS asset_os_name,
            pa.criticality AS asset_criticality,
            sa.raw_event,
            sa.ai_business_impact,
            sa.ai_recommended_action,
            sa.ai_likely_attack_type
        FROM security_alerts sa
        LEFT JOIN protected_assets pa ON pa.id = sa.asset_id
        WHERE sa.tenant_id = %s
          AND sa.id = %s
          AND sa.customer_visible = true;
        """,
        (tenant["id"], alert_id),
    )

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"tenant": tenant, "alert": _customer_safe_alert_detail_row(alert)}


@router.get("/assets/{short_code}")
def customer_assets(
    short_code: str,
    asset_status: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
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

    # Pull enrolled endpoint agents into protected_assets so Assets stays current.
    try:
        from app.services.agent_asset_sync import sync_tenant_endpoint_agents

        sync_tenant_endpoint_agents(tenant_id, short_code=tenant["short_code"])
    except Exception:
        pass

    appliances = fetch_all(
        """
        SELECT
            a.id::text AS appliance_id,
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

    page, page_size, offset = clamp_pagination(page, page_size)
    where = ["pa.tenant_id = %s"]
    params: list = [tenant_id]
    st = (asset_status or "").strip().lower()
    if st in ("active", "inactive", "unknown"):
        where.append("pa.status = %s")
        params.append(st)
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "COALESCE(pa.hostname, '') ILIKE %s OR "
            "COALESCE(pa.os_name, '') ILIKE %s OR "
            "COALESCE(pa.asset_type, '') ILIKE %s OR "
            "COALESCE(pa.owner, '') ILIKE %s OR "
            "COALESCE(a.appliance_name, '') ILIKE %s OR "
            "COALESCE(a.site_name, '') ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like, like, like, like])
    where_sql = " AND ".join(where)

    count_row = fetch_one(
        f"""
        SELECT count(*)::int AS total
        FROM protected_assets pa
        LEFT JOIN appliances a ON a.id = pa.appliance_id
        WHERE {where_sql};
        """,
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)

    assets = fetch_all(
        f"""
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
        WHERE {where_sql}
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
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )

    return {
        "tenant": tenant,
        "appliances": appliances,
        "assets": assets,
        **pagination_meta(total, page, page_size),
    }


@router.get("/assets/{short_code}/{asset_id}")
def customer_asset_detail(
    short_code: str,
    asset_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    KB-030: Tenant-scoped, read-only customer protected-asset detail.

    Looks up by asset_id (UUID). Returns only customer-safe fields.
    Optional LEFT JOIN to appliances for appliance_name/site_name only.
    Missing/wrong-tenant → 404. Does not expose IPs, details JSON,
    appliance_id, credentials, health_snapshot, or secrets.
    """
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # KB-011: see customer_dashboard() above for why this is 404, not 403.
    require_tenant_match(tenant["id"], current_user)

    asset = fetch_one(
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
          AND pa.id = %s;
        """,
        (tenant["id"], asset_id),
    )

    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    return {"tenant": tenant, "asset": asset}


@router.get("/appliances/{short_code}/{appliance_id}")
def customer_appliance_detail(
    short_code: str,
    appliance_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    KB-035: Tenant-scoped, read-only customer appliance detail.

    Looks up by appliance_id (UUID). Returns customer-safe posture fields,
    latest heartbeat metrics, and linked protected assets (safe list fields).
    Missing/wrong-tenant → 404. Does not expose IPs, health_snapshot,
    appliance_uuid, credentials, activation tokens, or secrets.
    """
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # KB-011: see customer_dashboard() above for why this is 404, not 403.
    require_tenant_match(tenant["id"], current_user)

    appliance = fetch_one(
        """
        SELECT
            a.id::text AS appliance_id,
            a.appliance_name,
            a.site_name,
            a.status,
            a.last_seen_at,
            a.agent_version,
            a.config_version,
            a.update_status,
            h.health_status,
            h.cpu_percent,
            h.memory_percent,
            h.disk_percent,
            h.heartbeat_at AS latest_heartbeat_at
        FROM appliances a
        LEFT JOIN LATERAL (
            SELECT
                health_status,
                cpu_percent,
                memory_percent,
                disk_percent,
                heartbeat_at
            FROM appliance_heartbeats h
            WHERE h.appliance_id = a.id
            ORDER BY h.heartbeat_at DESC
            LIMIT 1
        ) h ON true
        WHERE a.tenant_id = %s
          AND a.id = %s;
        """,
        (tenant["id"], appliance_id),
    )

    if not appliance:
        raise HTTPException(status_code=404, detail="Appliance not found")

    protected_assets = fetch_all(
        """
        SELECT
            pa.id::text AS asset_id,
            pa.hostname,
            pa.asset_type,
            pa.criticality,
            pa.status,
            pa.last_seen_at
        FROM protected_assets pa
        WHERE pa.tenant_id = %s
          AND pa.appliance_id = %s
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
        (tenant["id"], appliance_id),
    )

    appliance["protected_assets_count"] = len(protected_assets)
    appliance["protected_assets"] = protected_assets

    return {"tenant": tenant, "appliance": appliance}


@router.get("/reports/{short_code}")
def customer_reports(
    short_code: str,
    report_status: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    KB-024: Tenant-scoped customer monthly reports (published/archived only).

    Returns customer-safe fields from monthly_reports. Does not expose
    metrics JSON, report_file_path, drafts, secrets, or generation internals.
    Title is derived from report_month (no separate title column exists).
    """
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # KB-011: see customer_dashboard() above for why this is 404, not 403.
    require_tenant_match(tenant["id"], current_user)

    page, page_size, offset = clamp_pagination(page, page_size)
    where = ["tenant_id = %s", "status IN ('published', 'archived')"]
    params: list = [tenant["id"]]
    st = (report_status or "").strip().lower()
    if st in ("published", "archived"):
        where.append("status = %s")
        params.append(st)
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "('Monthly Security Report — ' || to_char(report_month, 'Mon YYYY')) ILIKE %s OR "
            "COALESCE(executive_summary, '') ILIKE %s OR "
            "to_char(report_month, 'YYYY-MM') ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like])
    where_sql = " AND ".join(where)

    count_row = fetch_one(
        f"SELECT count(*)::int AS total FROM monthly_reports WHERE {where_sql};",
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)

    rows = fetch_all(
        f"""
        SELECT
            id::text AS report_id,
            report_month,
            status,
            ('Monthly Security Report — ' || to_char(report_month, 'Mon YYYY')) AS title,
            executive_summary AS summary,
            created_at,
            published_at
        FROM monthly_reports
        WHERE {where_sql}
        ORDER BY report_month DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )

    return {"tenant": tenant, "reports": rows, **pagination_meta(total, page, page_size)}


@router.get("/reports/{short_code}/{report_id}")
def customer_report_detail(
    short_code: str,
    report_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    KB-031/067: Tenant-scoped, read-only customer monthly report detail.

    Looks up by report_id (UUID). Returns only customer-safe fields + projected sections.
    Filters status IN ('published', 'archived'). Draft/missing/wrong-tenant → 404.
    Does not expose raw metrics JSON, report_file_path, or secrets.
    """
    from uuid import UUID as _UUID

    from app.services.report_snapshot_service import get_safe_sections_for_report

    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # KB-011: see customer_dashboard() above for why this is 404, not 403.
    require_tenant_match(tenant["id"], current_user)

    report = fetch_one(
        """
        SELECT
            id::text AS report_id,
            report_month,
            status,
            ('Monthly Security Report — ' || to_char(report_month, 'Mon YYYY')) AS title,
            executive_summary AS summary,
            created_at,
            published_at
        FROM monthly_reports
        WHERE tenant_id = %s
          AND id = %s
          AND status IN ('published', 'archived');
        """,
        (tenant["id"], report_id),
    )

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        rid = _UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Report not found")

    report["sections"] = get_safe_sections_for_report(rid)
    return {"tenant": tenant, "report": report}


def _customer_report_download(short_code: str, report_id: str, current_user: Dict[str, Any], fmt: str):
    from uuid import UUID as _UUID

    from fastapi.responses import Response

    from app.services.report_export_service import build_pdf_bytes, build_xlsx_bytes, export_filename
    from app.services.report_snapshot_service import get_safe_sections_for_report

    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    require_tenant_match(tenant["id"], current_user)

    report = fetch_one(
        """
        SELECT
            id::text AS report_id,
            report_month::text,
            ('Monthly Security Report — ' || to_char(report_month, 'Mon YYYY')) AS title,
            executive_summary,
            published_at::text
        FROM monthly_reports
        WHERE tenant_id = %s
          AND id = %s
          AND status IN ('published', 'archived');
        """,
        (tenant["id"], report_id),
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        rid = _UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Report not found")

    sections = get_safe_sections_for_report(rid)
    if fmt == "pdf":
        content = build_pdf_bytes(
            title=report["title"],
            executive_summary=report.get("executive_summary"),
            published_at=report.get("published_at"),
            sections=sections,
        )
        media = "application/pdf"
        filename = export_filename(tenant["short_code"], report["report_month"], "pdf")
    else:
        content = build_xlsx_bytes(
            title=report["title"],
            executive_summary=report.get("executive_summary"),
            published_at=report.get("published_at"),
            sections=sections,
        )
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = export_filename(tenant["short_code"], report["report_month"], "xlsx")

    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/{short_code}/{report_id}/download.pdf")
def customer_report_download_pdf(
    short_code: str,
    report_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """KB-067: Customer PDF download for published/archived reports only."""
    return _customer_report_download(short_code, report_id, current_user, "pdf")


@router.get("/reports/{short_code}/{report_id}/download.xlsx")
def customer_report_download_xlsx(
    short_code: str,
    report_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """KB-067: Customer Excel download for published/archived reports only."""
    return _customer_report_download(short_code, report_id, current_user, "xlsx")


@router.get("/recommendations/{short_code}")
def customer_recommendations(
    short_code: str,
    rec_status: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    KB-026: Tenant-scoped customer-visible recommendations (all statuses).

    Returns only customer-safe fields. Filters customer_visible = true.
    Does not expose related_alert_id, related_incident_id, or secrets.
    """
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # KB-011: see customer_dashboard() above for why this is 404, not 403.
    require_tenant_match(tenant["id"], current_user)

    page, page_size, offset = clamp_pagination(page, page_size)
    where = ["tenant_id = %s", "customer_visible = true"]
    params: list = [tenant["id"]]
    st = (rec_status or "").strip().lower()
    if st in ("open", "in_progress", "accepted_risk", "completed", "dismissed"):
        where.append("status = %s")
        params.append(st)
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "title ILIKE %s OR "
            "COALESCE(description, '') ILIKE %s OR "
            "COALESCE(category, '') ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like, like])
    where_sql = " AND ".join(where)

    count_row = fetch_one(
        f"SELECT count(*)::int AS total FROM customer_recommendations WHERE {where_sql};",
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)

    rows = fetch_all(
        f"""
        SELECT
            id::text AS recommendation_id,
            title,
            description,
            priority,
            category,
            status,
            due_at,
            completed_at,
            created_at,
            updated_at
        FROM customer_recommendations
        WHERE {where_sql}
        ORDER BY
            CASE priority
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 4
                ELSE 5
            END,
            created_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )

    return {
        "tenant": tenant,
        "recommendations": rows,
        **pagination_meta(total, page, page_size),
    }


@router.get("/recommendations/{short_code}/{recommendation_id}")
def customer_recommendation_detail(
    short_code: str,
    recommendation_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    KB-027: Tenant-scoped, read-only customer recommendation detail.

    Looks up by recommendation_id (UUID). Returns only customer-safe fields.
    Filters customer_visible = true. Missing/hidden/wrong-tenant → 404.
    Does not expose related_alert_id, related_incident_id, or secrets.
    """
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # KB-011: see customer_dashboard() above for why this is 404, not 403.
    require_tenant_match(tenant["id"], current_user)

    recommendation = fetch_one(
        """
        SELECT
            id::text AS recommendation_id,
            title,
            description,
            priority,
            category,
            status,
            due_at,
            completed_at,
            created_at,
            updated_at
        FROM customer_recommendations
        WHERE tenant_id = %s
          AND id = %s
          AND customer_visible = true;
        """,
        (tenant["id"], recommendation_id),
    )

    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    return {"tenant": tenant, "recommendation": recommendation}


@router.get("/vulnerabilities/{short_code}/summary")
def customer_vulnerability_summary(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    KB-079: Customer-safe vulnerability *service* summary (not raw findings).
    Entitlement uses vulnerability_management flag (greenbone_enabled column).
    """
    tenant = fetch_one(
        """
        SELECT id::text, name, short_code, status
        FROM tenants
        WHERE short_code = %s;
        """,
        (short_code.upper(),),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    require_tenant_match(tenant["id"], current_user)

    ent = fetch_one(
        """
        SELECT greenbone_enabled, greenbone_cadence
        FROM tenant_entitlements
        WHERE tenant_id = %s::uuid;
        """,
        (tenant["id"],),
    )
    enabled = bool(ent and ent.get("greenbone_enabled"))
    cadence = (ent.get("greenbone_cadence") if ent else None) or "monthly"

    rec_row = fetch_one(
        """
        SELECT count(*)::int AS n
        FROM customer_recommendations
        WHERE tenant_id = %s::uuid
          AND customer_visible = true
          AND status = 'open'
          AND category = 'vulnerability';
        """,
        (tenant["id"],),
    )
    published_open = int(rec_row["n"]) if rec_row else 0

    activity = fetch_one(
        """
        SELECT max(last_seen_at)::text AS last_scan_activity_at
        FROM vulnerabilities
        WHERE tenant_id = %s::uuid
          AND status = 'open';
        """,
        (tenant["id"],),
    )
    last_activity = activity.get("last_scan_activity_at") if activity else None

    return {
        "tenant": {
            "short_code": tenant["short_code"],
            "name": tenant["name"],
        },
        "service_active": enabled,
        "cadence": cadence if enabled else "off",
        "published_open_recommendations": published_open,
        "last_scan_activity_at": last_activity if enabled else None,
    }


@router.get("/notifications/{short_code}")
def customer_notifications(
    short_code: str,
    notif_status: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    KB-033: Tenant-scoped, read-only customer notification history.

    Returns only customer-safe fields from notification_events.
    Does not expose recipient PII, provider IDs, error_message,
    incident_id/alert_id, or secrets.
    """
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # KB-011: see customer_dashboard() above for why this is 404, not 403.
    require_tenant_match(tenant["id"], current_user)

    page, page_size, offset = clamp_pagination(page, page_size)
    where = ["tenant_id = %s"]
    params: list = [tenant["id"]]
    st = (notif_status or "").strip().lower()
    if st:
        where.append("status = %s")
        params.append(st)
    q_clean = (q or "").strip()
    if q_clean:
        where.append(
            "("
            "notification_type ILIKE %s OR "
            "COALESCE(message_body, '') ILIKE %s"
            ")"
        )
        like = f"%{q_clean}%"
        params.extend([like, like])
    where_sql = " AND ".join(where)

    count_row = fetch_one(
        f"SELECT count(*)::int AS total FROM notification_events WHERE {where_sql};",
        tuple(params),
    )
    total = int((count_row or {}).get("total") or 0)

    rows = fetch_all(
        f"""
        SELECT
            id::text AS notification_id,
            notification_type,
            status,
            message_body,
            sent_at,
            delivered_at,
            created_at
        FROM notification_events
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )

    return {
        "tenant": tenant,
        "notifications": rows,
        **pagination_meta(total, page, page_size),
    }
