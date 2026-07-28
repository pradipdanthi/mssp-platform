"""KB-071: write structured rows into audit_logs."""

from __future__ import annotations

from typing import Any, Dict, Optional

from psycopg.types.json import Json

from app.db.session import fetch_one_write


def write_audit_event(
    *,
    action: str,
    entity_type: str,
    actor_user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    source_ip: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row = fetch_one_write(
        """
        INSERT INTO audit_logs (
            tenant_id, actor_user_id, action, entity_type, entity_id, source_ip, details
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING id::text, action, entity_type, entity_id::text, created_at::text;
        """,
        (
            tenant_id,
            actor_user_id,
            action,
            entity_type,
            entity_id,
            source_ip,
            Json(details or {}),
        ),
    )
    return row or {"action": action, "entity_type": entity_type, "details": details or {}}
