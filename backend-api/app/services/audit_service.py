"""KB-071/085: write structured rows into audit_logs."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from psycopg.types.json import Json

from app.db.session import fetch_one_write

logger = logging.getLogger(__name__)


def write_audit_event(
    *,
    action: str,
    entity_type: str,
    actor_user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    source_ip: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    actor_email: Optional[str] = None,
    actor_role: Optional[str] = None,
    action_status: str = "SUCCESS",
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
) -> Dict[str, Any]:
    status = (action_status or "SUCCESS").upper()
    if status not in ("SUCCESS", "FAILED"):
        status = "SUCCESS"
    try:
        row = fetch_one_write(
            """
            INSERT INTO audit_logs (
                tenant_id, actor_user_id, action, entity_type, entity_id, source_ip, details,
                actor_email, actor_role, action_status, resource_type, resource_id
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            RETURNING id::text, action, entity_type, entity_id::text, action_status, created_at::text;
            """,
            (
                tenant_id,
                actor_user_id,
                action,
                entity_type,
                entity_id,
                source_ip,
                Json(details or {}),
                actor_email,
                actor_role,
                status,
                resource_type or entity_type,
                resource_id or (str(entity_id) if entity_id else None),
            ),
        )
        return row or {"action": action, "entity_type": entity_type, "details": details or {}}
    except Exception:
        logger.exception("audit_logs write failed action=%s", action)
        return {"action": action, "entity_type": entity_type, "details": details or {}, "error": True}


def audit_from_user(
    user: Optional[Dict[str, Any]],
    *,
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    source_ip: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    action_status: str = "SUCCESS",
) -> Dict[str, Any]:
    user = user or {}
    return write_audit_event(
        action=action,
        entity_type=entity_type,
        actor_user_id=user.get("id"),
        tenant_id=tenant_id or user.get("tenant_id"),
        entity_id=entity_id,
        source_ip=source_ip,
        details=details,
        actor_email=user.get("email"),
        actor_role=user.get("role"),
        action_status=action_status,
        resource_type=entity_type,
        resource_id=entity_id,
    )
