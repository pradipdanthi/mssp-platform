import os
from contextlib import contextmanager
from typing import Any, Dict, List

import psycopg
from psycopg.rows import dict_row
import redis
from fastapi import FastAPI, HTTPException


APP_NAME = os.getenv("APP_NAME", "MSSP Control Plane API")
APP_ENV = os.getenv("APP_ENV", "development")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@contextmanager
def db_conn():
    conn = psycopg.connect(
        host=_env("POSTGRES_HOST", "postgres"),
        port=int(_env("POSTGRES_PORT", "5432")),
        dbname=_env("POSTGRES_DB", "mssp_control"),
        user=_env("POSTGRES_USER", "mssp_admin"),
        password=_env("POSTGRES_PASSWORD"),
        row_factory=dict_row,
        connect_timeout=5,
    )
    try:
        yield conn
    finally:
        conn.close()


def redis_client() -> redis.Redis:
    return redis.Redis(
        host=_env("REDIS_HOST", "redis"),
        port=int(_env("REDIS_PORT", "6379")),
        password=_env("REDIS_PASSWORD"),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def fetch_all(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return list(cur.fetchall())


def fetch_one(query: str, params: tuple = ()) -> Dict[str, Any]:
    rows = fetch_all(query, params)
    if not rows:
        return {}
    return rows[0]


app = FastAPI(
    title=APP_NAME,
    description="Backend API foundation for the MSSP Control Plane.",
    version="0.1.0",
)


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "service": "mssp-backend-api",
        "status": "running",
        "environment": APP_ENV,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    db_status = "unknown"
    redis_status = "unknown"

    try:
        row = fetch_one("SELECT 1 AS ok;")
        db_status = "ok" if row.get("ok") == 1 else "error"
    except Exception as exc:
        db_status = f"error: {exc}"

    try:
        pong = redis_client().ping()
        redis_status = "ok" if pong else "error"
    except Exception as exc:
        redis_status = f"error: {exc}"

    api_status = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return {
        "api": api_status,
        "service": "mssp-backend-api",
        "environment": APP_ENV,
        "database": db_status,
        "redis": redis_status,
    }


@app.get("/admin/dashboard")
def admin_dashboard() -> Dict[str, Any]:
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


@app.get("/admin/tenants")
def admin_tenants() -> Dict[str, Any]:
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


@app.get("/admin/appliances")
def admin_appliances() -> Dict[str, Any]:
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


@app.get("/admin/alerts")
def admin_alerts() -> Dict[str, Any]:
    rows = fetch_all(
        """
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
        ORDER BY sa.created_at DESC
        LIMIT 100;
        """
    )
    return {"alerts": rows}


@app.get("/admin/incidents")
def admin_incidents() -> Dict[str, Any]:
    rows = fetch_all(
        """
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
        ORDER BY i.created_at DESC
        LIMIT 100;
        """
    )
    return {"incidents": rows}


@app.get("/customer/dashboard/{short_code}")
def customer_dashboard(short_code: str) -> Dict[str, Any]:
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


@app.get("/customer/incidents/{short_code}")
def customer_incidents(short_code: str) -> Dict[str, Any]:
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

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
