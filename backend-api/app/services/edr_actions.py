"""KB-083/084: EDR containment, forensics, and action lifecycle execution."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

from app.db.session import db_transaction, fetch_one
from app.schemas.edr import EdrActionExecuteRequest, EdrActionType
from app.services.audit_service import audit_from_user
from app.services import edr_forensics_storage, shuffle_edr_client, wazuh_client
from app.services.appliance_manager_resolver import (
    primary_appliance_for_tenant,
    tenant_uses_appliance_manager,
)
from app.services import appliance_jobs as appliance_jobs_service
from app.services.endpoint_asset_resolve import resolve_endpoint_asset

logger = logging.getLogger(__name__)

# SOC analysts may execute containment from the MSSP/Admin portal (audited).
SOC_WRITE_ROLES = frozenset({"platform_admin", "soc_manager", "soc_analyst"})
CUSTOMER_ACTION_ROLES = frozenset({"customer_admin"})
READ_ONLY_CUSTOMER = frozenset({"customer_viewer"})

ISOLATE_AR_COMMAND = (os.getenv("EDR_WAZUH_ISOLATE_COMMAND") or "mssp-isolate-host").strip()
KILL_AR_COMMAND = (os.getenv("EDR_WAZUH_KILL_COMMAND") or "mssp-kill-process").strip()
BLOCK_HASH_AR_COMMAND = (os.getenv("EDR_WAZUH_BLOCK_HASH_COMMAND") or "mssp-block-hash").strip()

# Windows AR command names registered on the Manager (see kb090 / deploy helpers).
# Scripts on the endpoint are *.cmd wrappers calling PowerShell (no Python required).
WIN_ISOLATE_AR_COMMAND = (os.getenv("EDR_WAZUH_ISOLATE_COMMAND_WIN") or "mssp-isolate-host.cmd").strip()
WIN_KILL_AR_COMMAND = (os.getenv("EDR_WAZUH_KILL_COMMAND_WIN") or "mssp-kill-process.cmd").strip()
WIN_BLOCK_HASH_AR_COMMAND = (os.getenv("EDR_WAZUH_BLOCK_HASH_COMMAND_WIN") or "mssp-block-hash.cmd").strip()


def _resolve_ar_command(base_command: str, win_command: str, agent_id: Optional[str]) -> str:
    """Pick the OS-appropriate AR command name. Fail closed if OS is unknown."""
    if not agent_id:
        raise ValueError("agent_id is required to resolve the Active Response command")
    # Prefer protected_assets OS (works for appliance-local agents not on cloud Manager).
    asset = fetch_one(
        """
        SELECT os_name, details
        FROM protected_assets
        WHERE details->>'wazuh_agent_id' = %s
        ORDER BY updated_at DESC NULLS LAST
        LIMIT 1;
        """,
        (str(agent_id),),
    )
    if asset:
        blob = f"{asset.get('os_name') or ''} {asset.get('details') or ''}".lower()
        if "windows" in blob:
            return win_command
        if any(x in blob for x in ("linux", "ubuntu", "centos", "debian", "rhel")):
            return base_command
    if not wazuh_client.credentials_configured():
        raise ValueError("Wazuh credentials are not configured; cannot resolve agent OS")
    agent_os = wazuh_client.get_agent_os(agent_id)
    if agent_os == "windows":
        return win_command
    if agent_os == "linux":
        return base_command
    raise ValueError(
        f"Cannot dispatch containment: agent {agent_id} OS is unknown. "
        "Confirm the agent is active on the manager and OS inventory is populated."
    )


def _queue_appliance_ar_job(
    *,
    tenant_id: str,
    user: Dict[str, Any],
    execution_id: str,
    action_type: str,
    agent_id: str,
    ar_command: str,
    arguments: list,
) -> Tuple[str, str, str, None, None]:
    """Enqueue AR for appliance-local Manager; appliance pulls via heartbeat."""
    appliance = primary_appliance_for_tenant(tenant_id)
    if not appliance:
        raise ValueError(
            "Tenant is appliance-mode but no registered appliance found. "
            "Register the appliance before running containment."
        )
    job = appliance_jobs_service.enqueue_job(
        appliance_id=appliance["id"],
        tenant_id=tenant_id,
        job_type=action_type,
        payload={
            "agent_id": agent_id,
            "ar_command": ar_command,
            "arguments": [str(a) for a in arguments],
            "execution_id": execution_id,
        },
        edr_execution_id=execution_id,
        requested_by_user_id=user.get("id"),
    )
    if action_type == "UNISOLATE_HOST":
        phase = "Un-isolating"
    elif action_type == "ISOLATE_HOST":
        phase = "Isolating"
    else:
        phase = "Processing"
    msg = (
        f"{phase}… command queued for appliance {appliance.get('appliance_name')} "
        f"(job {job['id']}). The endpoint will update when the agent confirms release."
    )
    _update_execution(execution_id, "executing", msg)
    _audit_success(
        user,
        action_type=action_type,
        execution_id=execution_id,
        tenant_id=tenant_id,
        status="executing",
        message=msg,
        agent_id=agent_id,
        incident_number=None,
        tenant_short_code=None,
    )
    return execution_id, "executing", msg, None, None


def _dispatch_cloud_active_response(
    *,
    agent_id: str,
    ar_cmd: str,
    arguments: list[str],
    action_type: str,
    execution_id: str,
    tolerate_api_timeout: bool = False,
) -> Tuple[str, str]:
    """Run Wazuh AR on cloud manager; return (execution_status, message)."""
    _, note = wazuh_client.run_active_response_resilient(
        agent_id=agent_id,
        command=ar_cmd,
        arguments=arguments,
        tolerate_api_timeout=tolerate_api_timeout,
    )
    if action_type == "UNISOLATE_HOST":
        phase = "Un-isolating"
    elif action_type == "ISOLATE_HOST":
        phase = "Isolating"
    else:
        phase = "Processing"
    if note == "dispatched_pending_confirmation":
        msg = (
            f"{phase}… command sent to agent {agent_id}. "
            "Wazuh API timed out waiting for script completion; "
            "confirm on endpoint or wait for callback."
        )
        return "executing", msg
    msg = f"{phase}… Active Response dispatched to agent {agent_id}."
    return "executing", msg


def _tenant_deployment_mode(tenant_id: str) -> Optional[str]:
    row = fetch_one("SELECT deployment_mode FROM tenants WHERE id = %s::uuid;", (tenant_id,))
    return (row or {}).get("deployment_mode")


# 0 = hold until Un-isolate (MDR default). Never pass a number as AR extra_args[0]:
# Wazuh treats a numeric first argument as a timeout and then sends command=delete.
ISOLATE_SECONDS = (os.getenv("EDR_ISOLATE_SECONDS") or "0").strip()
ISOLATE_HOLD_ARG = "hold"


def _get_callback_base() -> str:
    from app.core.config import get_infra_settings
    return (
        os.getenv("EDR_PUBLIC_API_BASE")
        or os.getenv("MSSP_PUBLIC_API_BASE")
        or get_infra_settings().control_plane_url
    ).rstrip("/")

ALLOWED_CUSTOMER_ACTIONS = frozenset(
    {"ISOLATE_HOST", "UNISOLATE_HOST", "KILL_PROCESS", "COLLECT_FORENSICS", "BLOCK_HASH"}
)


def normalize_status(status: str) -> str:
    """Map legacy 'executed' to 'success' for API consumers."""
    if status == "executed":
        return "success"
    return status


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
        if action_type not in ALLOWED_CUSTOMER_ACTIONS:
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


def _wazuh_agent_from_asset(
    tenant_id: str,
    *,
    asset_id: Optional[str] = None,
    hostname: Optional[str] = None,
    alert_description: Optional[str] = None,
) -> Optional[str]:
    """Resolve local Manager agent id from protected_assets (appliance inventory)."""
    if asset_id:
        row = fetch_one(
            """
            SELECT details->>'wazuh_agent_id' AS wazuh_agent_id
            FROM protected_assets
            WHERE tenant_id = %s::uuid
              AND id = %s::uuid
              AND coalesce(details->>'wazuh_agent_id', '') <> ''
            LIMIT 1;
            """,
            (tenant_id, asset_id),
        )
        aid = str((row or {}).get("wazuh_agent_id") or "").strip()
        if aid:
            return aid
    linked = resolve_endpoint_asset(
        tenant_id, hostname=hostname, alert_description=alert_description
    )
    return (linked or {}).get("wazuh_agent_id")


def lookup_endpoint_from_incident(tenant_id: str, incident_id: str) -> Dict[str, Optional[str]]:
    """Hostname / agent id / IP from inventory when appliance alerts omit raw_event.agent."""
    row = fetch_one(
        """
        SELECT
            sa.destination_host,
            sa.alert_description,
            sa.asset_id::text AS asset_id,
            sa.raw_event
        FROM incidents i
        LEFT JOIN security_alerts sa ON sa.id = i.primary_alert_id
        WHERE i.tenant_id = %s::uuid AND i.id = %s::uuid
        LIMIT 1;
        """,
        (tenant_id, incident_id),
    )
    if not row:
        return {"agent_id": None, "hostname": None, "os_name": None, "ip": None}
    raw = row.get("raw_event") or {}
    raw_agent = raw.get("agent") if isinstance(raw, dict) and isinstance(raw.get("agent"), dict) else {}
    raw_id = str(raw_agent.get("id") or "").strip() or None
    linked = resolve_endpoint_asset(
        tenant_id,
        wazuh_agent_id=raw_id,
        hostname=row.get("destination_host") or raw_agent.get("name"),
        alert_description=row.get("alert_description"),
    )
    if row.get("asset_id") and not linked:
        asset = fetch_one(
            """
            SELECT
                hostname,
                os_name,
                CASE WHEN ip_address IS NOT NULL THEN host(ip_address) ELSE NULL END AS ip,
                details->>'wazuh_agent_id' AS wazuh_agent_id
            FROM protected_assets
            WHERE tenant_id = %s::uuid AND id = %s::uuid
            LIMIT 1;
            """,
            (tenant_id, row["asset_id"]),
        )
        if asset:
            linked = {
                "hostname": asset.get("hostname"),
                "os_name": asset.get("os_name"),
                "ip": asset.get("ip"),
                "wazuh_agent_id": str(asset.get("wazuh_agent_id") or "").strip() or None,
            }
    if not linked:
        return {
            "agent_id": raw_id,
            "hostname": row.get("destination_host"),
            "os_name": None,
            "ip": None,
        }
    return {
        "agent_id": linked.get("wazuh_agent_id") or raw_id,
        "hostname": linked.get("hostname") or row.get("destination_host"),
        "os_name": linked.get("os_name"),
        "ip": linked.get("ip"),
    }


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
    hostname = None
    asset_id = None
    description = None
    if aid:
        row = fetch_one(
            """
            SELECT raw_event, destination_host, asset_id::text AS asset_id, alert_description
            FROM security_alerts
            WHERE id = %s::uuid AND tenant_id = %s::uuid;
            """,
            (aid, tenant_id),
        )
        if row:
            raw = row.get("raw_event") or {}
            if isinstance(raw, dict):
                agent = raw.get("agent") if isinstance(raw.get("agent"), dict) else {}
                ag = str(agent.get("id") or "").strip()
                if ag:
                    return ag
            hostname = row.get("destination_host")
            asset_id = row.get("asset_id")
            description = row.get("alert_description")
    found = _wazuh_agent_from_asset(
        tenant_id,
        asset_id=asset_id,
        hostname=hostname,
        alert_description=description,
    )
    if found:
        return found
    if incident and incident.get("id"):
        filled = lookup_endpoint_from_incident(tenant_id, incident["id"])
        return filled.get("agent_id")
    return None


def _insert_execution(
    *,
    tenant_id: str,
    user_id: Optional[str],
    body: EdrActionExecuteRequest,
    incident_id: Optional[str],
    agent_id: Optional[str],
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
                agent_id or body.agent_id,
                str(body.pid) if body.pid is not None else (
                    f"name:{(body.process_name or '').strip()}" if (body.process_name or "").strip() else None
                ),
                body.file_hash_sha256,
                status,
                message[:2000],
            ),
        )
        row = cur.fetchone()
        return row["id"]


def _update_execution(
    execution_id: str,
    status: str,
    message: str,
    *,
    status_detail: Optional[str] = None,
    callback_payload: Optional[Dict[str, Any]] = None,
    verified: bool = False,
    external_ref: Optional[str] = None,
) -> None:
    with db_transaction() as cur:
        cur.execute(
            """
            UPDATE edr_action_executions
            SET status = %s,
                result_message = %s,
                status_detail = COALESCE(%s, status_detail),
                callback_payload = CASE
                    WHEN %s::jsonb IS NULL THEN callback_payload
                    ELSE COALESCE(callback_payload, '{}'::jsonb) || %s::jsonb
                END,
                verified_at = CASE WHEN %s THEN now() ELSE verified_at END,
                external_ref = COALESCE(%s, external_ref),
                updated_at = now()
            WHERE id = %s::uuid;
            """,
            (
                status,
                message[:2000],
                status_detail,
                json.dumps(callback_payload) if callback_payload is not None else None,
                json.dumps(callback_payload) if callback_payload is not None else None,
                verified,
                external_ref,
                execution_id,
            ),
        )


def verify_isolation_state(agent_id: str, *, expect_isolated: bool) -> Tuple[bool, str]:
    """
    Soft connectivity check only - NOT proof that firewall isolation worked.

    Isolated hosts should still reach the manager (AR allows manager IP), so
    status=active is expected both before and after isolate. This cannot confirm
    LAN/gateway blocking; treat results as advisory for operator follow-up.
    """
    try:
        info = wazuh_client.get_agent_status(agent_id)
    except Exception as exc:
        return False, f"Connectivity check failed: {exc}"
    status = str(info.get("status") or "").lower()
    if status in ("active", "connected"):
        if expect_isolated:
            return (
                True,
                f"Agent still reachable via manager (status={status}); "
                "firewall isolation not proven - confirm MSSP_ISOLATE_* rules on endpoint",
            )
        return True, f"Endpoint connectivity via manager OK (status={status})"
    return False, f"Endpoint not reachable for verification (status={status or 'unknown'})"


def apply_action_callback(
    *,
    execution_id: str,
    status: str,
    message: Optional[str] = None,
    error_log: Optional[str] = None,
    agent_id: Optional[str] = None,
    external_ref: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row = fetch_one(
        """
        SELECT id::text, tenant_id::text, action_type, target_agent_id, status AS current_status
        FROM edr_action_executions
        WHERE id = %s::uuid;
        """,
        (execution_id,),
    )
    if not row:
        raise ValueError("Action not found")

    mapped = {
        "executing": "executing",
        "success": "success",
        "failed": "failed",
        "timeout": "failed",
    }.get(status, status)
    detail = error_log or message or ""
    final_status = mapped
    verified = False

    aid = agent_id or row.get("target_agent_id")
    applied = None
    released = None
    if isinstance(payload, dict):
        if payload.get("applied") is not None:
            applied = bool(payload.get("applied"))
        elif isinstance(payload.get("payload"), dict) and payload["payload"].get("applied") is not None:
            applied = bool(payload["payload"].get("applied"))
        if payload.get("released") is not None:
            released = bool(payload.get("released"))
        elif isinstance(payload.get("payload"), dict) and payload["payload"].get("released") is not None:
            released = bool(payload["payload"].get("released"))

    # Explicit Un-isolate only. Ignore Wazuh timed command=delete callbacks on
    # an ISOLATE_HOST execution -- those auto-lift the host while the dashboard
    # still shows Isolated (or flap isolate/unisolate with the watchdog).
    if mapped == "success" and released is True and aid:
        if row["action_type"] != "UNISOLATE_HOST":
            detail = (
                (detail or "")
                + " (ignored auto-release callback; host stays isolated until Un-isolate)"
            ).strip()
        else:
            with db_transaction() as cur:
                cur.execute(
                    """
                    UPDATE edr_endpoint_isolation
                    SET isolation_status = 'restored', released_at = now()
                    WHERE tenant_id = %s::uuid AND agent_id = %s;
                    """,
                    (row["tenant_id"], aid),
                )
            final_status = "verified"
            verified = True
            detail = (detail or "Endpoint reported quarantine released; pre-isolate firewall restored").strip()
    # Endpoint-reported applied=true is the only path to isolate Verified (KB-091 Wave 1).
    elif mapped == "success" and row["action_type"] == "ISOLATE_HOST" and applied is True:
        final_status = "verified"
        verified = True
        detail = (detail or "Endpoint reported quarantine applied=true").strip()
    elif mapped == "success" and row["action_type"] == "ISOLATE_HOST" and applied is False:
        final_status = "failed"
        detail = (detail or "Endpoint reported quarantine applied=false").strip()
    elif mapped == "success" and row["action_type"] in ("ISOLATE_HOST", "UNISOLATE_HOST") and aid:
        ok, verify_msg = verify_isolation_state(
            aid, expect_isolated=(row["action_type"] == "ISOLATE_HOST")
        )
        detail = f"{detail}; {verify_msg}".strip("; ")
        if ok and row["action_type"] == "UNISOLATE_HOST":
            # Unisolate: agent-online is a reasonable restore signal.
            final_status = "verified"
            verified = True
        elif ok and row["action_type"] == "ISOLATE_HOST":
            # Do not promote isolate to verified on agent-online alone.
            detail = (
                f"{detail} (dispatched only - confirm MSSP isolation firewall "
                "policy on the endpoint; agent stay-online is expected)"
            )
        else:
            detail = f"{detail} (verification pending: {verify_msg})"
    elif mapped == "success" and row["action_type"] == "UNISOLATE_HOST" and applied is True:
        final_status = "verified"
        verified = True
    elif mapped == "success" and row["action_type"] == "KILL_PROCESS" and applied is True:
        final_status = "verified"
        verified = True
        detail = (detail or "Endpoint reported process kill applied=true").strip()
    elif mapped == "success" and row["action_type"] == "KILL_PROCESS" and applied is False:
        final_status = "failed"
        detail = (detail or "Endpoint reported process kill applied=false").strip()
    elif mapped == "success" and row["action_type"] == "BLOCK_HASH" and applied is True:
        final_status = "verified"
        verified = True
        detail = (detail or "Endpoint reported block-hash applied=true").strip()
    elif mapped == "success" and row["action_type"] == "BLOCK_HASH" and applied is False:
        final_status = "failed"
        detail = (detail or "Endpoint reported block-hash applied=false").strip()

    if (
        mapped == "success"
        and row["action_type"] == "UNISOLATE_HOST"
        and aid
        and released is not True
    ):
        with db_transaction() as cur:
            cur.execute(
                """
                UPDATE edr_endpoint_isolation
                SET isolation_status = 'restored', released_at = now()
                WHERE tenant_id = %s::uuid AND agent_id = %s;
                """,
                (row["tenant_id"], aid),
            )

    if (
        mapped == "success"
        and row["action_type"] == "ISOLATE_HOST"
        and aid
        and released is not True
        and applied is True
    ):
        with db_transaction() as cur:
            cur.execute(
                """
                UPDATE edr_endpoint_isolation
                SET isolation_status = 'isolated', isolated_at = now()
                WHERE tenant_id = %s::uuid AND agent_id = %s;
                """,
                (row["tenant_id"], aid),
            )

    _update_execution(
        execution_id,
        final_status,
        (message or detail or final_status)[:2000],
        status_detail=detail[:4000] if detail else None,
        callback_payload=payload or {"status": status},
        verified=verified,
        external_ref=external_ref,
    )
    return {
        "execution_id": execution_id,
        "status": normalize_status(final_status),
        "message": message or detail or final_status,
    }


def _create_forensic_artifact(
    *,
    tenant_id: str,
    execution_id: str,
    agent_id: Optional[str],
) -> Dict[str, Any]:
    with db_transaction() as cur:
        cur.execute(
            """
            INSERT INTO edr_forensic_artifacts (
                tenant_id, execution_id, agent_id, object_key, file_name,
                status, storage_backend, upload_expires_at
            )
            VALUES (
                %s::uuid, %s::uuid, %s, 'pending', 'triage.zip',
                'awaiting_upload', %s, now() + interval '1 hour'
            )
            RETURNING id::text;
            """,
            (tenant_id, execution_id, agent_id, edr_forensics_storage.storage_backend()),
        )
        artifact_id = cur.fetchone()["id"]

    key = edr_forensics_storage.object_key_for(
        tenant_id=tenant_id,
        endpoint_id=agent_id or "unknown",
        artifact_id=artifact_id,
    )
    with db_transaction() as cur:
        cur.execute(
            """
            UPDATE edr_forensic_artifacts
            SET object_key = %s, updated_at = now()
            WHERE id = %s::uuid;
            """,
            (key, artifact_id),
        )
    upload = edr_forensics_storage.build_upload_url(
        artifact_id=artifact_id, tenant_id=tenant_id, ttl_seconds=3600
    )
    return {"artifact_id": artifact_id, "object_key": key, **upload}


def execute_edr_action(
    user: Dict[str, Any],
    body: EdrActionExecuteRequest,
    *,
    source_ip: Optional[str] = None,
) -> Tuple[str, str, str, Optional[str], Optional[str]]:
    """
    Returns (execution_id, status, message, upload_url, forensic_artifact_id).
    """
    if not body.tenant_short_code:
        raise ValueError("tenant_short_code is required")
    tenant = _resolve_tenant(body.tenant_short_code)
    tenant_id = tenant["id"]
    assert_can_execute_action(user, tenant_id=tenant_id, action_type=body.action_type)
    # Stash for audit enrichment (who / portal / incident / source).
    user = dict(user)
    if source_ip:
        user["_audit_source_ip"] = source_ip

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
        agent_id=agent_id,
        status="pending",
        message="Queued",
    )
    _update_execution(execution_id, "executing", "Dispatching action")
    callback_url = f"{_get_callback_base()}/v1/edr/actions/callback"

    try:
        if body.action_type == "ISOLATE_HOST":
            if not body.confirm_isolation:
                _update_execution(
                    execution_id,
                    "failed",
                    "confirm_isolation must be true to isolate a host",
                )
                return execution_id, "failed", "Confirmation required for host isolation", None, None
            if not agent_id:
                raise ValueError("Could not resolve endpoint agent for isolation")
            ar_cmd = _resolve_ar_command(ISOLATE_AR_COMMAND, WIN_ISOLATE_AR_COMMAND, agent_id)
            # Appliance tenants: queue job for local Manager (do not hit cloud Wazuh).
            # extra_args: ["hold", execution_id, callback_url] -- never a number (Wazuh timeout).
            isolate_args = [ISOLATE_HOLD_ARG, execution_id, callback_url]
            if tenant_uses_appliance_manager(_tenant_deployment_mode(tenant_id)):
                return _queue_appliance_ar_job(
                    tenant_id=tenant_id,
                    user=user,
                    execution_id=execution_id,
                    action_type=body.action_type,
                    agent_id=agent_id,
                    ar_command=ar_cmd,
                    arguments=isolate_args,
                )
            st, msg = _dispatch_cloud_active_response(
                agent_id=agent_id,
                ar_cmd=ar_cmd,
                arguments=isolate_args,
                action_type=body.action_type,
                execution_id=execution_id,
                tolerate_api_timeout=True,
            )
            shuffle_edr_client.post_edr_workflow(
                {
                    "action": "ISOLATE_HOST",
                    "execution_id": execution_id,
                    "callback_url": callback_url,
                    "agent_id": agent_id,
                    "tenant_short_code": body.tenant_short_code,
                    "isolate_seconds": ISOLATE_SECONDS,
                    "status": "executing",
                }
            )
            # Agent remaining "active" is expected (manager IP is allow-listed) and does
            # NOT prove network quarantine. Mark dispatched; require endpoint applied=true.
            _, verify_msg = verify_isolation_state(agent_id, expect_isolated=True)
            hold = "until Un-isolate" if str(ISOLATE_SECONDS) in ("0", "") else f"auto-release ~{ISOLATE_SECONDS}s"
            msg = (
                f"{msg} "
                f"Network quarantine ({hold}). "
                "Confirm on host log: QUARANTINE ACTIVE applied=true (or FAILED applied=false)."
            )
            _update_execution(
                execution_id,
                st,
                f"{msg} ({verify_msg})",
            )
            _audit_success(
                user,
                action_type=body.action_type,
                execution_id=execution_id,
                tenant_id=tenant_id,
                status=st,
                message=msg,
                agent_id=agent_id,
                incident_number=body.incident_number or (incident or {}).get("incident_number"),
                tenant_short_code=body.tenant_short_code,
            )
            return execution_id, st, msg, None, None

        if body.action_type == "UNISOLATE_HOST":
            if not agent_id:
                raise ValueError("Could not resolve endpoint agent for un-isolate")
            # Pass "delete" so the AR script restores connectivity.
            ar_cmd = _resolve_ar_command(ISOLATE_AR_COMMAND, WIN_ISOLATE_AR_COMMAND, agent_id)
            unisolate_args = ["delete", execution_id, callback_url]
            if tenant_uses_appliance_manager(_tenant_deployment_mode(tenant_id)):
                return _queue_appliance_ar_job(
                    tenant_id=tenant_id,
                    user=user,
                    execution_id=execution_id,
                    action_type=body.action_type,
                    agent_id=agent_id,
                    ar_command=ar_cmd,
                    arguments=unisolate_args,
                )
            st, msg = _dispatch_cloud_active_response(
                agent_id=agent_id,
                ar_cmd=ar_cmd,
                arguments=unisolate_args,
                action_type=body.action_type,
                execution_id=execution_id,
                tolerate_api_timeout=True,
            )
            shuffle_edr_client.post_edr_workflow(
                {
                    "action": "UNISOLATE_HOST",
                    "execution_id": execution_id,
                    "callback_url": callback_url,
                    "agent_id": agent_id,
                    "tenant_short_code": body.tenant_short_code,
                    "status": "executing",
                }
            )
            _update_execution(execution_id, st, msg)
            _audit_success(
                user,
                action_type=body.action_type,
                execution_id=execution_id,
                tenant_id=tenant_id,
                status=st,
                message=msg,
                agent_id=agent_id,
                incident_number=body.incident_number or (incident or {}).get("incident_number"),
                tenant_short_code=body.tenant_short_code,
            )
            return execution_id, st, msg, None, None

        if body.action_type == "KILL_PROCESS":
            if body.pid is None and not (body.process_name or "").strip():
                raise ValueError("pid or process_name is required for KILL_PROCESS")
            if not agent_id:
                raise ValueError("Could not resolve endpoint agent for kill")
            ar_cmd = _resolve_ar_command(KILL_AR_COMMAND, WIN_KILL_AR_COMMAND, agent_id)
            proc_name = (body.process_name or "").strip()
            if body.list_only:
                if not proc_name:
                    raise ValueError("process_name is required when list_only=true")
                target_arg = f"enum={proc_name}"
                action_label = "LIST_PROCESSES"
            elif proc_name:
                target_arg = f"name={proc_name}"
                action_label = "KILL_PROCESS"
            else:
                target_arg = str(body.pid)
                action_label = "KILL_PROCESS"
            kill_args = [target_arg, str(execution_id), callback_url]
            # Pass execution_id so AR scripts can POST applied proof to callback_url.
            if tenant_uses_appliance_manager(_tenant_deployment_mode(tenant_id)):
                return _queue_appliance_ar_job(
                    tenant_id=tenant_id,
                    user=user,
                    execution_id=execution_id,
                    action_type=body.action_type,
                    agent_id=agent_id,
                    ar_command=ar_cmd,
                    arguments=kill_args,
                )
            wazuh_client.run_active_response(
                agent_id=agent_id,
                command=ar_cmd,
                arguments=kill_args,
            )
            shuffle_edr_client.post_edr_workflow(
                {
                    "action": action_label,
                    "execution_id": execution_id,
                    "callback_url": callback_url,
                    "agent_id": agent_id,
                    "pid": body.pid,
                    "process_name": proc_name or None,
                    "list_only": bool(body.list_only),
                    "tenant_short_code": body.tenant_short_code,
                    "status": "executing",
                }
            )
            if body.list_only:
                msg = (
                    f"Live process enum dispatched to agent {agent_id} name={proc_name}. "
                    "Awaiting endpoint callback with current PIDs."
                )
            elif proc_name:
                msg = (
                    f"Kill-by-name dispatched to agent {agent_id} name={proc_name}. "
                    "Endpoint resolves LIVE PIDs (not syscollector). "
                    "Status remains Dispatched until endpoint callback reports applied=true."
                )
            else:
                msg = (
                    f"Kill process command dispatched to agent {agent_id} pid={body.pid}. "
                    "Status remains Dispatched until endpoint callback reports applied=true."
                )
            _update_execution(execution_id, "executing", msg)
            _audit_success(
                user,
                action_type=body.action_type,
                execution_id=execution_id,
                tenant_id=tenant_id,
                status="executing",
                message=msg,
                agent_id=agent_id,
                incident_number=body.incident_number or (incident or {}).get("incident_number"),
                tenant_short_code=body.tenant_short_code,
            )
            return execution_id, "executing", msg, None, None

        if body.action_type == "COLLECT_FORENSICS":
            artifact = _create_forensic_artifact(
                tenant_id=tenant_id,
                execution_id=execution_id,
                agent_id=agent_id,
            )
            vr_msg = ""
            vr_ok = False
            try:
                from app.services import velociraptor_client as vr

                if vr.configured():
                    host_label = agent_id or body.tenant_short_code or "endpoint"
                    vr_job = vr.collect_artifacts(
                        hostname=str(host_label),
                        tenant_id=tenant_id,
                        execution_id=execution_id,
                    )
                    vr_ok = True
                    vr_msg = (
                        f"Velociraptor job {vr_job.get('job_id')} "
                        f"package={vr_job.get('package_id')} queued on DFIR bridge."
                    )
                    # Customer-safe collection metadata for /forensics
                    try:
                        from app.db.session import execute as _exec

                        _exec(
                            """
                            INSERT INTO tenant_forensics_collections (
                                tenant_id, collection_name, host_label, collection_scope,
                                status, package_size_bytes, download_available, summary,
                                related_event_title, requested_at, completed_at
                            ) VALUES (
                                %s::uuid, %s, %s, 'TRIAGE', 'RUNNING', 0, false, %s,
                                'SOC forensics collection', now(), NULL
                            );
                            """,
                            (
                                tenant_id,
                                f"Live DFIR package {vr_job.get('package_id', '')}"[:200],
                                str(host_label)[:120],
                                (
                                    vr_job.get("customer_safe_summary")
                                    or "Endpoint forensics collection started on DFIR engine."
                                )[:2000],
                            ),
                        )
                    except Exception:
                        logger.exception("Failed writing forensics collection metadata")
                else:
                    vr_msg = "Velociraptor bridge not configured; Shuffle/upload path only."
            except Exception as exc:  # noqa: BLE001
                vr_msg = f"Velociraptor bridge error: {exc}"[:240]
                logger.warning("Velociraptor collect failed: %s", exc)

            payload = {
                "action": "COLLECT_FORENSICS",
                "workflow": shuffle_edr_client.forensics_workflow_name(),
                "execution_id": execution_id,
                "callback_url": callback_url,
                "forensics_complete_url": f"{_get_callback_base()}/v1/edr/forensics/complete",
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "tenant_short_code": body.tenant_short_code,
                "incident_number": body.incident_number
                or (incident or {}).get("incident_number"),
                "artifact_id": artifact["artifact_id"],
                "object_key": artifact["object_key"],
                "upload_url": artifact["upload_url"],
                "upload_method": artifact["upload_method"],
                "upload_expires_at_epoch": artifact["expires_at_epoch"],
                "mode": "velociraptor_bridge_and_upload" if vr_ok else "direct_object_upload",
                "velociraptor_server": shuffle_edr_client.velociraptor_server_url() or None,
            }
            ok, shuffle_msg = shuffle_edr_client.post_edr_workflow(payload)
            status = "executing" if (ok or vr_ok) else "failed"
            msg = (
                f"Forensics collection started. {vr_msg} {shuffle_msg}"
            ).strip()
            _update_execution(execution_id, status if (ok or vr_ok) else "failed", msg)
            _audit_success(
                user,
                action_type=body.action_type,
                execution_id=execution_id,
                tenant_id=tenant_id,
                status=status if (ok or vr_ok) else "failed",
                message=msg,
                agent_id=agent_id,
                incident_number=body.incident_number or (incident or {}).get("incident_number"),
                tenant_short_code=body.tenant_short_code,
            )
            return (
                execution_id,
                status if (ok or vr_ok) else "failed",
                msg,
                artifact["upload_url"] if (ok or vr_ok) else None,
                artifact["artifact_id"] if (ok or vr_ok) else None,
            )

        if body.action_type == "BLOCK_HASH":
            h = (body.file_hash_sha256 or "").strip().lower()
            if not re.fullmatch(r"[a-f0-9]{64}", h):
                raise ValueError("file_hash_sha256 must be 64 hex characters")
            ar_msg = "Endpoint hash block skipped (no agent)"
            via_appliance = tenant_uses_appliance_manager(_tenant_deployment_mode(tenant_id))
            if agent_id and via_appliance:
                ar_cmd = _resolve_ar_command(BLOCK_HASH_AR_COMMAND, WIN_BLOCK_HASH_AR_COMMAND, agent_id)
                cb = (callback_url or "").strip()
                args = [h, execution_id]
                if cb:
                    args.append(cb)
                return _queue_appliance_ar_job(
                    tenant_id=tenant_id,
                    user=user,
                    execution_id=execution_id,
                    action_type=body.action_type,
                    agent_id=agent_id,
                    ar_command=ar_cmd,
                    arguments=args,
                )
            if agent_id and wazuh_client.credentials_configured():
                ar_cmd = _resolve_ar_command(BLOCK_HASH_AR_COMMAND, WIN_BLOCK_HASH_AR_COMMAND, agent_id)
                cb = (callback_url or "").strip()
                args = [h, execution_id]
                if cb:
                    args.append(cb)
                wazuh_client.run_active_response(
                    agent_id=agent_id,
                    command=ar_cmd,
                    arguments=args,
                )
                ar_msg = (
                    f"Hash block command dispatched to agent {agent_id} "
                    f"(denylist + AppLocker/WDAC attempt when available; "
                    f"hash denylist alone does NOT prevent execution until WDAC/AppLocker applies; "
                    f"awaiting endpoint applied=true/false callback)."
                )
            ok, shuffle_msg = shuffle_edr_client.post_edr_workflow(
                {
                    "action": "BLOCK_HASH",
                    "execution_id": execution_id,
                    "callback_url": callback_url,
                    "sha256": h,
                    "agent_id": agent_id,
                    "tenant_short_code": body.tenant_short_code,
                    "status": "executing",
                }
            )
            # Stay executing until endpoint callback proves applied=true|false.
            status = "executing" if (agent_id and wazuh_client.credentials_configured()) or ok else "failed"
            if not agent_id and not ok:
                status = "failed"
            msg = f"{ar_msg}; orchestration: {shuffle_msg}"
            _update_execution(execution_id, status, msg)
            _audit_success(
                user,
                action_type=body.action_type,
                execution_id=execution_id,
                tenant_id=tenant_id,
                status=status,
                message=msg,
                agent_id=agent_id,
                incident_number=body.incident_number or (incident or {}).get("incident_number"),
                tenant_short_code=body.tenant_short_code,
            )
            return execution_id, status, msg, None, None

        raise ValueError("Unknown action")
    except Exception as exc:
        logger.exception("EDR action failed execution_id=%s", execution_id)
        if (
            body.action_type in ("ISOLATE_HOST", "UNISOLATE_HOST")
            and wazuh_client.is_transient_ar_error(exc)
        ):
            phase = "Un-isolating" if body.action_type == "UNISOLATE_HOST" else "Isolating"
            msg = (
                f"{phase}… Wazuh manager timed out or agent flickered offline. "
                "Command may still be running on the endpoint; check status in a moment."
            )
            _update_execution(execution_id, "executing", msg)
            _audit_success(
                user,
                action_type=body.action_type,
                execution_id=execution_id,
                tenant_id=tenant_id,
                status="executing",
                message=msg,
                agent_id=agent_id,
                incident_number=body.incident_number
                or (incident or {}).get("incident_number"),
                tenant_short_code=body.tenant_short_code,
            )
            return execution_id, "executing", msg, None, None
        _update_execution(execution_id, "failed", str(exc)[:500])
        try:
            audit_from_user(
                user,
                action=f"EDR_{body.action_type}",
                entity_type="edr_action",
                entity_id=execution_id,
                tenant_id=tenant_id,
                source_ip=user.get("_audit_source_ip"),
                action_status="FAILED",
                details=_edr_audit_details(
                    user=user,
                    action_type=body.action_type,
                    status="failed",
                    message=str(exc)[:300],
                    agent_id=agent_id,
                    incident_number=body.incident_number
                    or (incident or {}).get("incident_number"),
                    tenant_short_code=body.tenant_short_code,
                    execution_id=execution_id,
                    error=str(exc)[:300],
                ),
            )
        except Exception:
            pass
        return execution_id, "failed", str(exc)[:500], None, None


def _portal_label(user: Dict[str, Any]) -> str:
    role = str(user.get("role") or "")
    if role.startswith("customer_"):
        return "customer_portal"
    return "mssp_admin_portal"


def _action_summary(action_type: str, *, agent_id: Optional[str], incident_number: Optional[str]) -> str:
    host = f" agent {agent_id}" if agent_id else ""
    incident = f" (incident {incident_number})" if incident_number else ""
    labels = {
        "ISOLATE_HOST": f"Isolated/quarantined endpoint{host}{incident}",
        "UNISOLATE_HOST": f"Released endpoint from quarantine{host}{incident}",
        "KILL_PROCESS": f"Requested process kill on endpoint{host}{incident}",
        "BLOCK_HASH": f"Requested hash block on endpoint{host}{incident}",
        "COLLECT_FORENSICS": f"Requested forensic collection on endpoint{host}{incident}",
    }
    return labels.get(action_type, f"EDR action {action_type}{host}{incident}")


def _edr_audit_details(
    *,
    user: Dict[str, Any],
    action_type: str,
    status: str,
    message: str,
    agent_id: Optional[str],
    incident_number: Optional[str],
    tenant_short_code: Optional[str],
    execution_id: str,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    details: Dict[str, Any] = {
        "summary": _action_summary(
            action_type, agent_id=agent_id, incident_number=incident_number
        ),
        "status": status,
        "message": (message or "")[:500],
        "agent_id": agent_id,
        "incident_number": incident_number,
        "tenant_short_code": tenant_short_code,
        "execution_id": execution_id,
        "portal": _portal_label(user),
        "actor_email": user.get("email"),
        "actor_role": user.get("role"),
    }
    if error:
        details["error"] = error
    return details


def request_live_processes(
    user: Dict[str, Any],
    *,
    tenant_id: str,
    tenant_short_code: str,
    agent_id: str,
    process_name: str,
    timeout_seconds: int = 45,
) -> Dict[str, Any]:
    """Dispatch enum= AR and wait for endpoint callback with live PIDs."""
    import time

    name = (process_name or "").strip()
    if not name:
        raise ValueError("process_name is required")
    if not agent_id:
        raise ValueError("agent_id is required")

    body = EdrActionExecuteRequest(
        action_type="KILL_PROCESS",
        tenant_short_code=tenant_short_code,
        agent_id=agent_id,
        process_name=name,
        list_only=True,
    )
    execution_id, status, message, _, _ = execute_edr_action(user, body)
    deadline = time.time() + max(5, int(timeout_seconds))
    last_row: Optional[Dict[str, Any]] = None
    while time.time() < deadline:
        last_row = fetch_one(
            """
            SELECT id::text, status, result_message, callback_payload
            FROM edr_action_executions
            WHERE id = %s::uuid;
            """,
            (execution_id,),
        )
        if last_row and last_row.get("status") in ("verified", "failed", "success"):
            break
        time.sleep(2)

    processes: list[Dict[str, Any]] = []
    payload = (last_row or {}).get("callback_payload") or {}
    if isinstance(payload, dict):
        raw = payload.get("processes")
        if raw is None and isinstance(payload.get("payload"), dict):
            raw = payload["payload"].get("processes")
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                try:
                    pid = int(item.get("pid"))
                except (TypeError, ValueError):
                    continue
                processes.append(
                    {
                        "pid": pid,
                        "name": item.get("name"),
                        "path": item.get("path"),
                    }
                )

    final_status = normalize_status((last_row or {}).get("status") or status)
    return {
        "execution_id": execution_id,
        "status": final_status,
        "message": (last_row or {}).get("result_message") or message,
        "processes": processes,
        "source": "endpoint_live",
        "scan_time": None,
        "stale": False,
    }


def _audit_success(
    user: Dict[str, Any],
    *,
    action_type: str,
    execution_id: str,
    tenant_id: str,
    status: str,
    message: str,
    agent_id: Optional[str],
    incident_number: Optional[str] = None,
    tenant_short_code: Optional[str] = None,
) -> None:
    try:
        audit_from_user(
            user,
            action=f"EDR_{action_type}",
            entity_type="edr_action",
            entity_id=execution_id,
            tenant_id=tenant_id,
            source_ip=user.get("_audit_source_ip"),
            action_status="SUCCESS" if status != "failed" else "FAILED",
            details=_edr_audit_details(
                user=user,
                action_type=action_type,
                status=status,
                message=message,
                agent_id=agent_id,
                incident_number=incident_number,
                tenant_short_code=tenant_short_code,
                execution_id=execution_id,
            ),
        )
    except Exception:
        logger.exception("EDR audit write failed")
