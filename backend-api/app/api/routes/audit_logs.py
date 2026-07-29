"""KB-085: Audit log list APIs for Admin and Customer portals."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_current_user, require_roles, require_tenant_match
from app.db.session import fetch_all, fetch_one

admin_router = APIRouter(prefix="/admin", tags=["admin-audit"])
customer_router = APIRouter(prefix="/customer", tags=["customer-audit"])
v1_admin_router = APIRouter(prefix="/v1/admin", tags=["v1-admin-audit"])
v1_customer_router = APIRouter(prefix="/v1/customer", tags=["v1-customer-audit"])

ADMIN_SOC_ROLES = ("platform_admin", "soc_manager", "soc_analyst")


def _audit_select() -> str:
    return """
        SELECT
            al.id::text,
            al.tenant_id::text,
            t.name AS tenant_name,
            t.short_code,
            al.actor_user_id::text,
            COALESCE(al.actor_email, pu.email) AS actor_email,
            COALESCE(al.actor_role, pu.role) AS actor_role,
            al.action,
            al.entity_type,
            al.entity_id::text,
            COALESCE(al.resource_type, al.entity_type) AS resource_type,
            COALESCE(al.resource_id, al.entity_id::text) AS resource_id,
            host(al.source_ip) AS source_ip,
            COALESCE(al.action_status, 'SUCCESS') AS action_status,
            al.details,
            al.created_at::text AS timestamp,
            al.created_at::text
        FROM audit_logs al
        LEFT JOIN tenants t ON t.id = al.tenant_id
        LEFT JOIN platform_users pu ON pu.id = al.actor_user_id
    """


def _list_admin_audit(
    *,
    tenant_short_code: Optional[str],
    actor_email: Optional[str],
    action_type: Optional[str],
    limit: int,
) -> Dict[str, List[Dict[str, Any]]]:
    clauses = ["1=1"]
    params: list = []
    if tenant_short_code:
        clauses.append("t.short_code = %s")
        params.append(tenant_short_code.upper())
    if actor_email:
        clauses.append("lower(COALESCE(al.actor_email, pu.email)) = lower(%s)")
        params.append(actor_email.strip())
    if action_type:
        clauses.append("al.action = %s")
        params.append(action_type.strip())
    params.append(max(1, min(limit, 500)))
    rows = fetch_all(
        f"""
        {_audit_select()}
        WHERE {' AND '.join(clauses)}
        ORDER BY al.created_at DESC
        LIMIT %s;
        """,
        tuple(params),
    )
    return {"audit_logs": rows}


@admin_router.get("/audit-logs")
def admin_audit_logs(
    tenant_short_code: Optional[str] = Query(default=None, max_length=32),
    actor_email: Optional[str] = Query(default=None, max_length=320),
    action_type: Optional[str] = Query(default=None, max_length=120),
    limit: int = Query(default=200, ge=1, le=500),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, List[Dict[str, Any]]]:
    _ = current_user
    return _list_admin_audit(
        tenant_short_code=tenant_short_code,
        actor_email=actor_email,
        action_type=action_type,
        limit=limit,
    )


@v1_admin_router.get("/audit-logs")
def v1_admin_audit_logs(
    tenant_short_code: Optional[str] = Query(default=None, max_length=32),
    actor_email: Optional[str] = Query(default=None, max_length=320),
    action_type: Optional[str] = Query(default=None, max_length=120),
    limit: int = Query(default=200, ge=1, le=500),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, List[Dict[str, Any]]]:
    _ = current_user
    return _list_admin_audit(
        tenant_short_code=tenant_short_code,
        actor_email=actor_email,
        action_type=action_type,
        limit=limit,
    )


def _customer_audit(short_code: str, user: Dict[str, Any], limit: int) -> Dict[str, Any]:
    tenant = fetch_one(
        "SELECT id::text, short_code, name FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    require_tenant_match(tenant["id"], user)
    rows = fetch_all(
        f"""
        {_audit_select()}
        WHERE al.tenant_id = %s::uuid
        ORDER BY al.created_at DESC
        LIMIT %s;
        """,
        (tenant["id"], max(1, min(limit, 200))),
    )
    # Customer-safe: drop raw failed password details if any
    safe = []
    for row in rows:
        details = row.get("details") if isinstance(row.get("details"), dict) else {}
        scrubbed = {k: v for k, v in details.items() if k not in ("password", "password_hash", "token")}
        item = dict(row)
        item["details"] = scrubbed
        safe.append(item)
    return {"tenant": {"short_code": tenant["short_code"], "name": tenant["name"]}, "audit_logs": safe}


@customer_router.get("/audit-logs/{short_code}")
def customer_audit_logs(
    short_code: str,
    limit: int = Query(default=100, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    if current_user.get("role") not in ("customer_admin", "customer_viewer"):
        raise HTTPException(status_code=403, detail="Customer role required")
    return _customer_audit(short_code, current_user, limit)


@v1_customer_router.get("/audit-logs")
def v1_customer_audit_logs(
    tenant_short_code: Optional[str] = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    if current_user.get("role") not in ("customer_admin", "customer_viewer"):
        raise HTTPException(status_code=403, detail="Customer role required")
    code = tenant_short_code or ""
    if not code:
        row = fetch_one(
            "SELECT short_code FROM tenants WHERE id = %s::uuid;",
            (current_user.get("tenant_id"),),
        )
        code = (row or {}).get("short_code") or ""
    if not code:
        raise HTTPException(status_code=400, detail="tenant_short_code is required")
    return _customer_audit(code, current_user, limit)
