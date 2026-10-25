"""
NikTiar Secure Edge — appliance heartbeat + admin inventory (KB-114).

MVP: accepts edge node heartbeats; optional bearer token; stores last-seen in Postgres.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user, require_roles
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_all, fetch_one_write

router = APIRouter(tags=["secure-edge"])


class SecureEdgeHeartbeat(BaseModel):
    hostname: str = Field(..., min_length=1, max_length=128)
    tenant_short_code: Optional[str] = Field(default=None, max_length=32)
    status: str = Field(default="online", max_length=32)
    version: str = Field(default="0.1.0", max_length=32)
    capabilities: List[str] = Field(default_factory=list)


@router.post("/api/v1/secure-edge/heartbeat")
def secure_edge_heartbeat(
    body: SecureEdgeHeartbeat,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Appliance-facing; bearer optional in MVP (lab)."""
    _ = authorization  # reserved for appliance API key hardening
    caps = json.dumps(body.capabilities or [])
    row = fetch_one_write(
        """
        INSERT INTO secure_edge_nodes (
            hostname, tenant_short_code, status, version, capabilities,
            last_heartbeat_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s::jsonb, NOW(), NOW()
        )
        ON CONFLICT (hostname) DO UPDATE SET
            tenant_short_code = EXCLUDED.tenant_short_code,
            status = EXCLUDED.status,
            version = EXCLUDED.version,
            capabilities = EXCLUDED.capabilities,
            last_heartbeat_at = NOW(),
            updated_at = NOW()
        RETURNING hostname, status, last_heartbeat_at;
        """,
        (
            body.hostname,
            (body.tenant_short_code or "").upper() or None,
            body.status,
            body.version,
            caps,
        ),
    )
    return {
        "ok": True,
        "hostname": row["hostname"] if row else body.hostname,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/api/v1/secure-edge/events")
def secure_edge_events(
    payload: Dict[str, Any],
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Placeholder ingest for WAF/CrowdSec block events."""
    _ = authorization
    count = len(payload.get("events") or [])
    return {"ok": True, "accepted": count}


@router.get("/admin/secure-edge/nodes")
def admin_secure_edge_nodes(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    require_roles(current_user, ADMIN_SOC_ROLES)
    nodes = fetch_all(
        """
        SELECT hostname, tenant_short_code, status, version, capabilities,
               last_heartbeat_at, created_at, updated_at
        FROM secure_edge_nodes
        ORDER BY last_heartbeat_at DESC NULLS LAST;
        """
    )
    return {"nodes": nodes or [], "count": len(nodes or [])}
