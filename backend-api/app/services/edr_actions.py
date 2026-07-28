"""KB-083: EDR containment and forensic action execution."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple

from app.db.session import db_transaction, fetch_one
from app.schemas.edr import EdrActionExecuteRequest, EdrActionType
from app.services import shuffle_edr_client, wazuh_client

logger = logging.getLogger(__name__)

SOC_WRITE_ROLES = frozenset({"platform_admin", "soc_manager"})
CUSTOMER_ACTION_ROLES = frozenset({"customer_admin"})
READ_ONLY_CUSTOMER = frozenset({"customer_viewer"})

ISOLATE_AR_COMMAND = "firewall-drop"
KILL_AR_COMMAND_LINUX = "restart-wazuh"
BLOCK_HASH_LIST_KEY = "edr_blocked_hashes"


def assert_can_execute_action(
    user: Dict[str, Any],
    *,
    tenant_id: str,
    action_type: EdrActionType,
) -> None:
    role = str(user.get("role") or "")
    if role in SOC_WRITE_ROLES:
        return
    if role in READ_ONLY_CUSTOMER:
        raise PermissionError("customer_viewer cannot execute EDR actions")
    if role in CUSTOMER_ACTION_ROLES:
        if str(user.get("tenant_id")) != str(tenant_id):
            raise PermissionError("tenant mismatch")
        if action_type not in ("ISOLATE_HOST", "KILL_PROCESS", "COLLECT_FORENSICS", "BLOCK_HASH"):
            raise PermissionError("action not allowed")
        return
    raise PermissionError("role not permitted for EDR actions")


def _resolve_tenant(short_code: str) -> Dict[str, Any]:
    row = fetch_one(
        """
        SELECT id::text AS id, short_code
        FROM tenants
        WHERE short_code = %s AND status = 'active';
        """,
        (short_code.upper(),),
    )
    if not row:
        raise ValueError("Tenant not found")
    return row


def _resolve_incident(
    tenant_id: str,
    *,
    incident_id: Optional[str],
    incident_number: Optional[str],
) -> Optional[Dict[str, Any]]:
    if incident_id:
        return fetch_one(
            """
            SELECT id::text AS id, incident_number, primary_alert_id::text AS primary_alert_id
            FROM incidents
            WHERE tenant_id = %s::uuid AND id = %s::uuid;
            """,
            (tenant_id, incident_id),
        )
    if incident_number:
        return fetch_one(
            """
            SELECT id::text AS id, incident_number, primary_alert_id::text AS primary_alert_id
            FROM incidents
            WHERE tenant_id = %s::uuid AND incident_number = %s;
            """,
            (tenant_id, incident_number),
        )
    return None


def _agent_from_context(
    tenant_id: str,
    *,
    agent_id: Optional[str],
    alert_id: Optional[str],
    incident: Optional[Dict[str, Any]],
) -> Optional[str]:
    if agent_id:
        return agent_id.strip()
    aid = alert_id
    if not aid and incident and incident.get("primary_alert_id"):
        aid = incident["primary_alert_id"]
    if not aid:
        return None
    row = fetch_one(
        """
        SELECT raw_event
        FROM security_alerts
        WHERE id = %s::uuid AND tenant_id = %s::uuid;
        """,
        (aid, tenant_id),
    )
    if not row:
        return None
    raw = row.get("raw_event") or {}
    if isinstance(raw, dict):
        agent = raw.get("agent") if isinstance(raw.get("agent"), dict) else {}
        ag = str(agent.get("id") or "").strip()
        return ag or None
    return None


def _insert_execution(
    *,
    tenant_id: str,
    user_id: Optional[str],
    body: EdrActionExecuteRequest,
    incident_id: Optional[str],
    status: str,
    message: str,
) -> str:
    with db_transaction() as cur:
        cur.execute(
            """
            INSERT INTO edr_action_executions (
                tenant_id, incident_id, alert_id, requested_by_user_id,
                action_type, target_agent_id, target_pid, target_hash,
                status, result_message
            )
            VALUES (
                %s::uuid, %s::uuid, %s::uuid, %s::uuid,
                %s, %s, %s, %s,
                %s, %s
            )
            RETURNING id::text;
            """,
            (
                tenant_id,
                incident_id,
                body.alert_id,
                user_id,
                body.action_type,
                body.agent_id,
                str(body.pid) if body.pid is not None else None,
                body.file_hash_sha256,
                status,
                message[:2000],
            ),
        )
        row = cur.fetchone()
        return row["id"]


def _update_execution(execution_id: str, status: str, message: str) -> None:
    with db_transaction() as cur:
        cur.execute(
            """
            UPDATE edr_action_executions
            SET status = %s, result_message = %s, updated_at = now()
            WHERE id = %s::uuid;
            """,
            (status, message[:2000], execution_id),
        )


def execute_edr_action(
    user: Dict[str, Any],
    body: EdrActionExecuteRequest,
) -> Tuple[str, str, str]:
    """
    Returns (execution_id, status, message).
  """
    if not body.tenant_short_code:
        raise ValueError("tenant_short_code is required")
    tenant = _resolve_tenant(body.tenant_short_code)
    tenant_id = tenant["id"]
    assert_can_execute_action(user, tenant_id=tenant_id, action_type=body.action_type)

    incident = _resolve_incident(
        tenant_id,
        incident_id=body.incident_id,
        incident_number=body.incident_number,
    )
    incident_id = incident["id"] if incident else None
    agent_id = _agent_from_context(
        tenant_id,
        agent_id=body.agent_id,
        alert_id=body.alert_id,
        incident=incident,
    )

    execution_id = _insert_execution(
        tenant_id=tenant_id,
        user_id=user.get("id"),
        body=body,
        incident_id=incident_id,
        status="pending",
        message="Queued",
    )

    try:
        if body.action_type == "ISOLATE_HOST":
            if not body.confirm_isolation:
                _update_execution(
                    execution_id,
                    "failed",
                    "confirm_isolation must be true to isolate a host",
                )
                return execution_id, "failed", "Confirmation required for host isolation"
            if not agent_id:
                raise ValueError("Could not resolve Wazuh agent for isolation")
            wazuh_client.run_active_response(agent_id=agent_id, command=ISOLATE_AR_COMMAND)
            with db_transaction() as cur:
                cur.execute(
                    """
                    INSERT INTO edr_endpoint_isolation (tenant_id, agent_id, isolated_by_user_id)
                    VALUES (%s::uuid, %s, %s::uuid)
                    ON CONFLICT (tenant_id, agent_id)
                    DO UPDATE SET isolated_at = now(), isolated_by_user_id = EXCLUDED.isolated_by_user_id;
                    """,
                    (tenant_id, agent_id, user.get("id")),
                )
            msg = f"Isolation active response sent to agent {agent_id}"
            _update_execution(execution_id, "executed", msg)
            return execution_id, "executed", msg

        if body.action_type == "KILL_PROCESS":
            if body.pid is None:
                raise ValueError("pid is required for KILL_PROCESS")
            if not agent_id:
                raise ValueError("Could not resolve Wazuh agent for kill")
            ok, shuffle_msg = shuffle_edr_client.post_edr_workflow(
                {
                    "action": "KILL_PROCESS",
                    "agent_id": agent_id,
                    "pid": body.pid,
                    "tenant_short_code": body.tenant_short_code,
                }
            )
            if ok:
                try:
                    wazuh_client.run_custom_active_response(
                        agent_id=agent_id,
                        command_line=f"kill-process-{body.pid}",
                    )
                except wazuh_client.WazuhClientError as exc:
                    logger.warning("Wazuh AR kill fallback: %s", exc)
            status = "executed" if ok else "failed"
            _update_execution(execution_id, status, shuffle_msg)
            return execution_id, status, shuffle_msg

        if body.action_type == "COLLECT_FORENSICS":
            payload = {
                "action": "COLLECT_FORENSICS",
                "workflow": shuffle_edr_client.forensics_workflow_name(),
                "agent_id": agent_id,
                "tenant_short_code": body.tenant_short_code,
                "incident_number": body.incident_number or (incident or {}).get("incident_number"),
                "mode": "velociraptor_server"
                if shuffle_edr_client.velociraptor_server_url()
                else "offline_collector_via_shuffle",
            }
            ok, shuffle_msg = shuffle_edr_client.post_edr_workflow(payload)
            status = "executed" if ok else "failed"
            _update_execution(execution_id, status, shuffle_msg)
            return execution_id, status, shuffle_msg

        if body.action_type == "BLOCK_HASH":
            h = (body.file_hash_sha256 or "").strip().lower()
            if not re.fullmatch(r"[a-f0-9]{64}", h):
                raise ValueError("file_hash_sha256 must be 64 hex characters")
            ok, shuffle_msg = shuffle_edr_client.post_edr_workflow(
                {
                    "action": "BLOCK_HASH",
                    "sha256": h,
                    "tenant_short_code": body.tenant_short_code,
                }
            )
            if ok and agent_id and wazuh_client.credentials_configured():
                try:
                    wazuh_client.run_active_response(
                        agent_id=agent_id,
                        command="custom-block-hash",
                        arguments=[h],
                    )
                except wazuh_client.WazuhClientError:
                    logger.warning("Global hash block AR not configured; Shuffle path only")
            status = "executed" if ok else "failed"
            _update_execution(execution_id, status, shuffle_msg)
            return execution_id, status, shuffle_msg

        raise ValueError("Unknown action")
    except Exception as exc:
        logger.exception("EDR action failed execution_id=%s", execution_id)
        _update_execution(execution_id, "failed", str(exc)[:500])
        return execution_id, "failed", str(exc)[:500]
