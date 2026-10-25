"""
NikTiar Secure Edge — hybrid multi-tenant edge (KB-114 / KB-114b).

- Shared mode: one edge hosts many tenants by Host/SNI (SMB).
- Dedicated mode: edge pinned to one tenant (enterprise).
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user, require_roles, require_tenant_match
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import execute, fetch_all, fetch_one, fetch_one_write

router = APIRouter(tags=["secure-edge"])


class SecureEdgeHeartbeat(BaseModel):
    hostname: str = Field(..., min_length=1, max_length=128)
    tenant_short_code: Optional[str] = Field(default=None, max_length=32)
    status: str = Field(default="online", max_length=32)
    version: str = Field(default="0.2.0", max_length=32)
    deployment_mode: str = Field(default="shared", max_length=16)
    capabilities: List[str] = Field(default_factory=list)


class SecureEdgeSiteCreate(BaseModel):
    tenant_short_code: str = Field(..., min_length=2, max_length=32)
    public_hostname: str = Field(..., min_length=1, max_length=253)
    origin_url: str = Field(..., min_length=3, max_length=512)
    edge_node_hostname: Optional[str] = Field(default=None, max_length=128)
    waf_profile: str = Field(default="standard", max_length=32)
    tls_mode: str = Field(default="http_only", max_length=16)
    enabled: bool = True
    notes: Optional[str] = Field(default=None, max_length=1024)
    zone_settings: Optional[Dict[str, Any]] = None


class SecureEdgeSitePatch(BaseModel):
    origin_url: Optional[str] = Field(default=None, max_length=512)
    edge_node_hostname: Optional[str] = Field(default=None, max_length=128)
    waf_profile: Optional[str] = Field(default=None, max_length=32)
    tls_mode: Optional[str] = Field(default=None, max_length=16)
    enabled: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=1024)


class SecureEdgeEventsIn(BaseModel):
    edge_hostname: str = Field(..., min_length=1, max_length=128)
    events: List[Dict[str, Any]] = Field(default_factory=list)


def _bearer_ok(authorization: Optional[str], expected: Optional[str]) -> bool:
    if not expected:
        return True
    if not authorization or not authorization.lower().startswith("bearer "):
        return False
    return authorization.split(" ", 1)[1].strip() == expected


def _bump_shared_nodes() -> None:
    execute(
        """
        UPDATE secure_edge_nodes
        SET last_config_version = last_config_version + 1, updated_at = NOW()
        WHERE deployment_mode = 'shared';
        """
    )


def _bump_config_version(edge_hostname: Optional[str] = None) -> None:
    if edge_hostname:
        execute(
            """
            UPDATE secure_edge_nodes
            SET last_config_version = last_config_version + 1, updated_at = NOW()
            WHERE hostname = %s;
            """,
            (edge_hostname,),
        )
    else:
        _bump_shared_nodes()


@router.post("/api/v1/secure-edge/heartbeat")
def secure_edge_heartbeat(
    body: SecureEdgeHeartbeat,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    mode = (body.deployment_mode or "shared").lower()
    if mode not in ("shared", "dedicated"):
        raise HTTPException(status_code=400, detail="deployment_mode must be shared|dedicated")

    existing = fetch_one(
        "SELECT appliance_token FROM secure_edge_nodes WHERE hostname = %s;",
        (body.hostname,),
    )
    if existing and not _bearer_ok(authorization, existing.get("appliance_token")):
        raise HTTPException(status_code=401, detail="Invalid appliance token")

    caps = json.dumps(body.capabilities or [])
    row = fetch_one_write(
        """
        INSERT INTO secure_edge_nodes (
            hostname, tenant_short_code, status, version, capabilities,
            deployment_mode, last_heartbeat_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s::jsonb, %s, NOW(), NOW()
        )
        ON CONFLICT (hostname) DO UPDATE SET
            tenant_short_code = COALESCE(EXCLUDED.tenant_short_code, secure_edge_nodes.tenant_short_code),
            status = EXCLUDED.status,
            version = EXCLUDED.version,
            capabilities = EXCLUDED.capabilities,
            deployment_mode = EXCLUDED.deployment_mode,
            last_heartbeat_at = NOW(),
            updated_at = NOW()
        RETURNING hostname, status, deployment_mode, last_config_version, last_heartbeat_at;
        """,
        (
            body.hostname,
            (body.tenant_short_code or "").upper() or None,
            body.status,
            body.version,
            caps,
            mode,
        ),
    )
    return {
        "ok": True,
        "hostname": row.get("hostname") if row else body.hostname,
        "deployment_mode": row.get("deployment_mode") if row else mode,
        "config_version": row.get("last_config_version") if row else 0,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/v1/secure-edge/config")
def secure_edge_config(
    hostname: str = Query(..., min_length=1, max_length=128),
    mode: Optional[str] = Query(default=None, max_length=16),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    node = fetch_one(
        """
        SELECT hostname, tenant_short_code, deployment_mode, last_config_version, appliance_token
        FROM secure_edge_nodes WHERE hostname = %s;
        """,
        (hostname,),
    )
    if not node:
        node = {
            "hostname": hostname,
            "tenant_short_code": None,
            "deployment_mode": (mode or "shared").lower(),
            "last_config_version": 0,
            "appliance_token": None,
        }
    if not _bearer_ok(authorization, node.get("appliance_token")):
        raise HTTPException(status_code=401, detail="Invalid appliance token")

    dep_mode = (mode or node.get("deployment_mode") or "shared").lower()
    if dep_mode == "dedicated":
        tenant = (node.get("tenant_short_code") or "").upper()
        sites = []
        if tenant:
            sites = fetch_all(
                """
                SELECT id::text, tenant_short_code, public_hostname, origin_url,
                       edge_node_hostname, waf_profile, tls_mode, enabled,
                       COALESCE(zone_settings, '{}'::jsonb) AS zone_settings
                FROM secure_edge_sites
                WHERE enabled = TRUE
                  AND UPPER(tenant_short_code) = %s
                  AND (edge_node_hostname IS NULL OR edge_node_hostname = %s)
                ORDER BY public_hostname;
                """,
                (tenant, hostname),
            )
    else:
        sites = fetch_all(
            """
            SELECT id::text, tenant_short_code, public_hostname, origin_url,
                   edge_node_hostname, waf_profile, tls_mode, enabled,
                   COALESCE(zone_settings, '{}'::jsonb) AS zone_settings
            FROM secure_edge_sites
            WHERE enabled = TRUE
              AND (edge_node_hostname IS NULL OR edge_node_hostname = %s)
            ORDER BY public_hostname;
            """,
            (hostname,),
        )

    return {
        "hostname": hostname,
        "deployment_mode": dep_mode,
        "config_version": int(node.get("last_config_version") or 0),
        "sites": sites or [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/api/v1/secure-edge/events")
def secure_edge_events(
    payload: SecureEdgeEventsIn,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    node = fetch_one(
        "SELECT appliance_token FROM secure_edge_nodes WHERE hostname = %s;",
        (payload.edge_hostname,),
    )
    if node and not _bearer_ok(authorization, node.get("appliance_token")):
        raise HTTPException(status_code=401, detail="Invalid appliance token")

    accepted = 0
    for ev in (payload.events or [])[:100]:
        execute(
            """
            INSERT INTO secure_edge_events (
                tenant_short_code, edge_hostname, public_hostname,
                event_type, severity, summary, details
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb);
            """,
            (
                ev.get("tenant_short_code") or None,
                payload.edge_hostname,
                ev.get("public_hostname"),
                (ev.get("event_type") or "unknown")[:64],
                (ev.get("severity") or "info")[:16],
                (ev.get("summary") or "event")[:512],
                json.dumps(ev.get("details") or {}),
            ),
        )
        accepted += 1
    return {"ok": True, "accepted": accepted}


@router.get("/admin/secure-edge/summary")
def admin_secure_edge_summary(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    nodes = fetch_all(
        """
        SELECT hostname, deployment_mode, status, version, last_heartbeat_at, last_config_version
        FROM secure_edge_nodes
        ORDER BY last_heartbeat_at DESC NULLS LAST;
        """
    )
    site_count = fetch_one("SELECT COUNT(*)::int AS n FROM secure_edge_sites WHERE enabled = TRUE;")
    event_count = fetch_one(
        """
        SELECT COUNT(*)::int AS n FROM secure_edge_events
        WHERE created_at > NOW() - INTERVAL '24 hours';
        """
    )
    recent = fetch_all(
        """
        SELECT id, tenant_short_code, edge_hostname, public_hostname,
               event_type, severity, summary, created_at
        FROM secure_edge_events
        ORDER BY created_at DESC
        LIMIT 25;
        """
    )
    return {
        "nodes": nodes or [],
        "enabled_sites": (site_count or {}).get("n") or 0,
        "events_24h": (event_count or {}).get("n") or 0,
        "recent_events": recent or [],
        "dashboard_hint": "Appliance UI: http://<edge-ip>:9080/ (default user admin)",
    }


@router.get("/admin/secure-edge/nodes")
def admin_secure_edge_nodes(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    nodes = fetch_all(
        """
        SELECT hostname, tenant_short_code, status, version, capabilities,
               deployment_mode, last_config_version, last_heartbeat_at,
               created_at, updated_at,
               CASE WHEN appliance_token IS NULL OR appliance_token = '' THEN FALSE ELSE TRUE END AS token_set
        FROM secure_edge_nodes
        ORDER BY last_heartbeat_at DESC NULLS LAST;
        """
    )
    return {"nodes": nodes or [], "count": len(nodes or [])}


@router.post("/admin/secure-edge/nodes/{hostname}/token")
def admin_issue_edge_token(
    hostname: str,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    token = secrets.token_urlsafe(32)
    row = fetch_one_write(
        """
        UPDATE secure_edge_nodes
        SET appliance_token = %s, updated_at = NOW()
        WHERE hostname = %s
        RETURNING hostname;
        """,
        (token, hostname),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Edge node not found — wait for heartbeat first")
    return {"hostname": hostname, "appliance_token": token}


@router.get("/admin/secure-edge/sites")
def admin_list_sites(
    tenant_short_code: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    if tenant_short_code:
        sites = fetch_all(
            """
            SELECT id::text, tenant_short_code, public_hostname, origin_url,
                   edge_node_hostname, waf_profile, tls_mode, enabled, notes,
                   created_at, updated_at
            FROM secure_edge_sites
            WHERE UPPER(tenant_short_code) = %s
            ORDER BY public_hostname;
            """,
            (tenant_short_code.upper(),),
        )
    else:
        sites = fetch_all(
            """
            SELECT id::text, tenant_short_code, public_hostname, origin_url,
                   edge_node_hostname, waf_profile, tls_mode, enabled, notes,
                   created_at, updated_at
            FROM secure_edge_sites
            ORDER BY tenant_short_code, public_hostname;
            """
        )
    return {"sites": sites or [], "count": len(sites or [])}


@router.post("/admin/secure-edge/sites")
def admin_create_site(
    body: SecureEdgeSiteCreate,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    tls = body.tls_mode if body.tls_mode in ("off", "http_only", "acme") else "http_only"
    row = fetch_one_write(
        """
        INSERT INTO secure_edge_sites (
            tenant_short_code, public_hostname, origin_url, edge_node_hostname,
            waf_profile, tls_mode, enabled, notes, zone_settings, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW()
        )
        RETURNING id::text, tenant_short_code, public_hostname, origin_url,
                  edge_node_hostname, waf_profile, tls_mode, enabled, zone_settings;
        """,
        (
            body.tenant_short_code.upper(),
            body.public_hostname.lower().strip(),
            body.origin_url.strip(),
            body.edge_node_hostname,
            body.waf_profile,
            tls,
            body.enabled,
            body.notes,
            json.dumps(body.zone_settings or {}),
        ),
    )
    _bump_config_version(body.edge_node_hostname)
    if not body.edge_node_hostname:
        _bump_shared_nodes()
    execute(
        """
        UPDATE tenant_entitlements te
        SET secure_edge_enabled = TRUE
        FROM tenants t
        WHERE te.tenant_id = t.id AND UPPER(t.short_code) = %s;
        """,
        (body.tenant_short_code.upper(),),
    )
    return {"ok": True, "site": row}


@router.put("/admin/secure-edge/sites/{site_id}/zone-settings")
def admin_put_zone_settings(
    site_id: UUID,
    settings: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Cloudflare-parity per-zone security settings (WAF/firewall/ssl/cache/rate limit)."""
    _ = current_user
    row = fetch_one_write(
        """
        UPDATE secure_edge_sites
        SET zone_settings = %s::jsonb, updated_at = NOW()
        WHERE id = %s::uuid
        RETURNING id::text, public_hostname, zone_settings, edge_node_hostname;
        """,
        (json.dumps(settings or {}), str(site_id)),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")
    _bump_config_version(row.get("edge_node_hostname"))
    _bump_shared_nodes()
    return {"ok": True, "site": row}


@router.patch("/admin/secure-edge/sites/{site_id}")
def admin_patch_site(
    site_id: UUID,
    body: SecureEdgeSitePatch,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    current = fetch_one(
        "SELECT * FROM secure_edge_sites WHERE id = %s::uuid;",
        (str(site_id),),
    )
    if not current:
        raise HTTPException(status_code=404, detail="Site not found")
    origin = body.origin_url if body.origin_url is not None else current["origin_url"]
    edge = body.edge_node_hostname if body.edge_node_hostname is not None else current["edge_node_hostname"]
    profile = body.waf_profile if body.waf_profile is not None else current["waf_profile"]
    tls = body.tls_mode if body.tls_mode is not None else current["tls_mode"]
    enabled = body.enabled if body.enabled is not None else current["enabled"]
    notes = body.notes if body.notes is not None else current["notes"]
    row = fetch_one_write(
        """
        UPDATE secure_edge_sites SET
            origin_url = %s,
            edge_node_hostname = %s,
            waf_profile = %s,
            tls_mode = %s,
            enabled = %s,
            notes = %s,
            updated_at = NOW()
        WHERE id = %s::uuid
        RETURNING id::text, tenant_short_code, public_hostname, origin_url,
                  edge_node_hostname, waf_profile, tls_mode, enabled;
        """,
        (origin, edge, profile, tls, enabled, notes, str(site_id)),
    )
    _bump_config_version(edge)
    _bump_shared_nodes()
    return {"ok": True, "site": row}


@router.delete("/admin/secure-edge/sites/{site_id}")
def admin_delete_site(
    site_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    row = fetch_one_write(
        """
        DELETE FROM secure_edge_sites WHERE id = %s::uuid
        RETURNING id::text, edge_node_hostname;
        """,
        (str(site_id),),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")
    _bump_config_version(row.get("edge_node_hostname"))
    _bump_shared_nodes()
    return {"ok": True, "deleted": row["id"]}


@router.get("/admin/secure-edge/events")
def admin_list_events(
    limit: int = Query(default=50, ge=1, le=500),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    rows = fetch_all(
        """
        SELECT id, tenant_short_code, edge_hostname, public_hostname,
               event_type, severity, summary, details, created_at
        FROM secure_edge_events
        ORDER BY created_at DESC
        LIMIT %s;
        """,
        (limit,),
    )
    return {"events": rows or [], "count": len(rows or [])}


@router.get("/customer/secure-edge/{short_code}/sites")
def customer_list_sites(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    require_tenant_match(tenant["id"], current_user)
    sites = fetch_all(
        """
        SELECT public_hostname, origin_url, waf_profile, tls_mode, enabled,
               edge_node_hostname, updated_at
        FROM secure_edge_sites
        WHERE UPPER(tenant_short_code) = %s
        ORDER BY public_hostname;
        """,
        (short_code.upper(),),
    )
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "sites": sites or [],
        "deployment_hint": (
            "Hybrid: unpinned sites land on shared SMB edges; "
            "set edge_node_hostname for dedicated enterprise appliances."
        ),
    }


@router.get("/customer/secure-edge/{short_code}/summary")
def customer_secure_edge_summary(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    require_tenant_match(tenant["id"], current_user)
    ent = fetch_one(
        """
        SELECT COALESCE(secure_edge_enabled, FALSE) AS secure_edge_enabled
        FROM tenant_entitlements WHERE tenant_id = %s::uuid;
        """,
        (tenant["id"],),
    )
    sites = fetch_all(
        """
        SELECT public_hostname, origin_url, tls_mode, enabled, edge_node_hostname, updated_at
        FROM secure_edge_sites
        WHERE UPPER(tenant_short_code) = %s
        ORDER BY public_hostname;
        """,
        (short_code.upper(),),
    )
    events = fetch_all(
        """
        SELECT event_type, severity, summary, public_hostname, created_at
        FROM secure_edge_events
        WHERE UPPER(COALESCE(tenant_short_code, '')) = %s
           OR public_hostname IN (
                SELECT public_hostname FROM secure_edge_sites
                WHERE UPPER(tenant_short_code) = %s
           )
        ORDER BY created_at DESC
        LIMIT 50;
        """,
        (short_code.upper(), short_code.upper()),
    )
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "enabled": bool((ent or {}).get("secure_edge_enabled")) or bool(sites),
        "sites": sites or [],
        "events": events or [],
        "site_count": len(sites or []),
        "event_count": len(events or []),
    }
