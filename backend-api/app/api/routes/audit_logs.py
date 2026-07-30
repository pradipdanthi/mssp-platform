"""KB-085+: Audit log list + detail APIs for Admin and Customer portals."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_current_user, require_roles, require_tenant_match
from app.db.session import fetch_all, fetch_one
from app.services.list_pagination import clamp_pagination, pagination_meta

admin_router = APIRouter(prefix="/admin", tags=["admin-audit"])
customer_router = APIRouter(prefix="/customer", tags=["customer-audit"])
v1_admin_router = APIRouter(prefix="/v1/admin", tags=["v1-admin-audit"])
v1_customer_router = APIRouter(prefix="/v1/customer", tags=["v1-customer-audit"])

ADMIN_SOC_ROLES = ("platform_admin", "soc_manager", "soc_analyst")

ACTION_LABELS = {
    "EDR_ISOLATE_HOST": "Isolate / quarantine host",
    "EDR_UNISOLATE_HOST": "Un-isolate / release host",
    "EDR_KILL_PROCESS": "Kill process",
    "EDR_BLOCK_HASH": "Block file hash",
    "EDR_COLLECT_FORENSICS": "Collect forensics",
    "LOGIN_SUCCESS": "Login succeeded",
    "LOGIN_FAILURE": "Login failed",
    "PASSWORD_CHANGE": "Password changed",
}


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


def _enrich_row(row: Dict[str, Any], *, scrub: bool = False) -> Dict[str, Any]:
    item = dict(row)
    details = item.get("details") if isinstance(item.get("details"), dict) else {}
    if scrub:
        details = {
            k: v
            for k, v in details.items()
            if k not in ("password", "password_hash", "token", "token_hash", "api_key")
        }
    action = str(item.get("action") or "")
    summary = details.get("summary") if isinstance(details.get("summary"), str) else None
    if not summary:
        summary = ACTION_LABELS.get(action, action.replace("_", " ").title())
    item["details"] = details
    item["action_label"] = ACTION_LABELS.get(action, action)
    item["summary"] = summary
    item["portal"] = details.get("portal")
    return item


def _list_admin_audit(
    *,
    tenant_short_code: Optional[str],
    actor_email: Optional[str],
    action_type: Optional[str],
    q: Optional[str],
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    page, page_size, offset = clamp_pagination(page, page_size)
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
    if q and q.strip():
        like = f"%{q.strip()}%"
        clauses.append(
            """(
                COALESCE(al.actor_email, pu.email, '') ILIKE %s
                OR al.action ILIKE %s
                OR COALESCE(al.entity_type, '') ILIKE %s
                OR COALESCE(t.name, '') ILIKE %s
                OR COALESCE(t.short_code, '') ILIKE %s
                OR COALESCE(al.details->>'summary', '') ILIKE %s
                OR COALESCE(al.details->>'incident_number', '') ILIKE %s
                OR COALESCE(al.details->>'agent_id', '') ILIKE %s
                OR host(al.source_ip)::text ILIKE %s
            )"""
        )
        params.extend([like] * 9)

    where = " AND ".join(clauses)
    total_row = fetch_one(
        f"""
        SELECT COUNT(*)::int AS total
        FROM audit_logs al
        LEFT JOIN tenants t ON t.id = al.tenant_id
        LEFT JOIN platform_users pu ON pu.id = al.actor_user_id
        WHERE {where};
        """,
        tuple(params),
    )
    total = int((total_row or {}).get("total") or 0)
    rows = fetch_all(
        f"""
        {_audit_select()}
        WHERE {where}
        ORDER BY al.created_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return {
        "audit_logs": [_enrich_row(r) for r in rows],
        **pagination_meta(total, page, page_size),
    }


def _get_admin_audit(audit_id: str) -> Dict[str, Any]:
    row = fetch_one(
        f"""
        {_audit_select()}
        WHERE al.id = %s::uuid;
        """,
        (audit_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return {"audit_log": _enrich_row(row)}


@admin_router.get("/audit-logs")
def admin_audit_logs(
    tenant_short_code: Optional[str] = Query(default=None, max_length=32),
    actor_email: Optional[str] = Query(default=None, max_length=320),
    action_type: Optional[str] = Query(default=None, max_length=120),
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    limit: Optional[int] = Query(default=None, ge=1, le=500),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    # Backward compatible: old clients sending only limit → treat as page 1.
    if limit is not None and page == 1 and page_size == 25:
        page_size = min(limit, 200)
    return _list_admin_audit(
        tenant_short_code=tenant_short_code,
        actor_email=actor_email,
        action_type=action_type,
        q=q,
        page=page,
        page_size=page_size,
    )


@admin_router.get("/audit-logs/{audit_id}")
def admin_audit_log_detail(
    audit_id: str,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    return _get_admin_audit(audit_id)


@v1_admin_router.get("/audit-logs")
def v1_admin_audit_logs(
    tenant_short_code: Optional[str] = Query(default=None, max_length=32),
    actor_email: Optional[str] = Query(default=None, max_length=320),
    action_type: Optional[str] = Query(default=None, max_length=120),
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    return _list_admin_audit(
        tenant_short_code=tenant_short_code,
        actor_email=actor_email,
        action_type=action_type,
        q=q,
        page=page,
        page_size=page_size,
    )


@v1_admin_router.get("/audit-logs/{audit_id}")
def v1_admin_audit_log_detail(
    audit_id: str,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    return _get_admin_audit(audit_id)


def _customer_audit(
    short_code: str,
    user: Dict[str, Any],
    *,
    q: Optional[str],
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    tenant = fetch_one(
        "SELECT id::text, short_code, name FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    require_tenant_match(tenant["id"], user)
    page, page_size, offset = clamp_pagination(page, page_size)
    clauses = ["al.tenant_id = %s::uuid"]
    params: list = [tenant["id"]]
    if q and q.strip():
        like = f"%{q.strip()}%"
        clauses.append(
            """(
                COALESCE(al.actor_email, pu.email, '') ILIKE %s
                OR al.action ILIKE %s
                OR COALESCE(al.details->>'summary', '') ILIKE %s
                OR COALESCE(al.details->>'incident_number', '') ILIKE %s
            )"""
        )
        params.extend([like] * 4)
    where = " AND ".join(clauses)
    total_row = fetch_one(
        f"""
        SELECT COUNT(*)::int AS total
        FROM audit_logs al
        LEFT JOIN platform_users pu ON pu.id = al.actor_user_id
        WHERE {where};
        """,
        tuple(params),
    )
    total = int((total_row or {}).get("total") or 0)
    rows = fetch_all(
        f"""
        {_audit_select()}
        WHERE {where}
        ORDER BY al.created_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    safe = [_enrich_row(row, scrub=True) for row in rows]
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "audit_logs": safe,
        **pagination_meta(total, page, page_size),
    }


def _customer_audit_detail(short_code: str, audit_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    tenant = fetch_one(
        "SELECT id::text, short_code, name FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    require_tenant_match(tenant["id"], user)
    row = fetch_one(
        f"""
        {_audit_select()}
        WHERE al.id = %s::uuid AND al.tenant_id = %s::uuid;
        """,
        (audit_id, tenant["id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "audit_log": _enrich_row(row, scrub=True),
    }


@customer_router.get("/audit-logs/{short_code}")
def customer_audit_logs(
    short_code: str,
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    if current_user.get("role") not in ("customer_admin", "customer_viewer"):
        raise HTTPException(status_code=403, detail="Customer role required")
    if limit is not None and page == 1 and page_size == 25:
        page_size = min(limit, 200)
    return _customer_audit(short_code, current_user, q=q, page=page, page_size=page_size)


@customer_router.get("/audit-logs/{short_code}/{audit_id}")
def customer_audit_log_detail(
    short_code: str,
    audit_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    if current_user.get("role") not in ("customer_admin", "customer_viewer"):
        raise HTTPException(status_code=403, detail="Customer role required")
    return _customer_audit_detail(short_code, audit_id, current_user)


@v1_customer_router.get("/audit-logs")
def v1_customer_audit_logs(
    tenant_short_code: Optional[str] = Query(default=None, max_length=32),
    q: Optional[str] = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
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
    return _customer_audit(code, current_user, q=q, page=page, page_size=page_size)


@v1_customer_router.get("/audit-logs/{audit_id}")
def v1_customer_audit_log_detail(
    audit_id: str,
    tenant_short_code: Optional[str] = Query(default=None, max_length=32),
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
    return _customer_audit_detail(code, audit_id, current_user)
