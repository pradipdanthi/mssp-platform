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
ISOLATE_SECONDS = (os.getenv("EDR_ISOLATE_SECONDS") or "120").strip()
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
                str(body.pid) if body.pid is not None else None,
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
        if "applied" in payload:
            applied = bool(payload.get("applied"))
        if "released" in payload:
            released = bool(payload.get("released"))

    # Auto-release / explicit release callback: restore isolation row, keep prior verified.
    if mapped == "success" and released is True and aid:
        with db_transaction() as cur:
            cur.execute(
                """
                UPDATE edr_endpoint_isolation
                SET isolation_status = 'restored', released_at = now()
                WHERE tenant_id = %s::uuid AND agent_id = %s;
                """,
                (row["tenant_id"], aid),
            )
        # Never downgrade a previously verified isolate execution on auto-release.
        if row["action_type"] == "ISOLATE_HOST" and str(row.get("current_status") or "") == "verified":
            final_status = "verified"
            verified = True
        elif row["action_type"] == "UNISOLATE_HOST":
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
        and applied is not False
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
            # extra_args: [seconds, execution_id] - endpoint callbacks use execution_id (KB-091).
            wazuh_client.run_active_response(
                agent_id=agent_id,
                command=ar_cmd,
                arguments=[ISOLATE_SECONDS, execution_id],
            )
            with db_transaction() as cur:
                cur.execute(
                    """
                    INSERT INTO edr_endpoint_isolation (
                        tenant_id, agent_id, isolated_by_user_id, isolation_status
                    )
                    VALUES (%s::uuid, %s, %s::uuid, 'isolated')
                    ON CONFLICT (tenant_id, agent_id)
                    DO UPDATE SET
                        isolated_at = now(),
                        isolated_by_user_id = EXCLUDED.isolated_by_user_id,
                        isolation_status = 'isolated',
                        released_at = NULL;
                    """,
                    (tenant_id, agent_id, user.get("id")),
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
            msg = (
                f"Network quarantine command dispatched to agent {agent_id} "
                f"(auto-release ~{ISOLATE_SECONDS}s). "
                "This is default-deny all traffic except Manager/DHCP/loopback - not ICMP-only. "
                "Confirm on host log: QUARANTINE ACTIVE applied=true (or FAILED applied=false)."
            )
            _update_execution(
                execution_id,
                "success",
                f"{msg} ({verify_msg})",
            )
            _audit_success(
                user,
                action_type=body.action_type,
                execution_id=execution_id,
                tenant_id=tenant_id,
                status="success",
                message=msg,
                agent_id=agent_id,
                incident_number=body.incident_number or (incident or {}).get("incident_number"),
                tenant_short_code=body.tenant_short_code,
            )
            return execution_id, "success", msg, None, None

        if body.action_type == "UNISOLATE_HOST":
            if not agent_id:
                raise ValueError("Could not resolve endpoint agent for un-isolate")
            # Pass "delete" so the AR script restores connectivity.
            ar_cmd = _resolve_ar_command(ISOLATE_AR_COMMAND, WIN_ISOLATE_AR_COMMAND, agent_id)
            wazuh_client.run_active_response(
                agent_id=agent_id,
                command=ar_cmd,
                arguments=["delete", execution_id],
            )
            with db_transaction() as cur:
                cur.execute(
                    """
                    UPDATE edr_endpoint_isolation
                    SET isolation_status = 'restored', released_at = now()
                    WHERE tenant_id = %s::uuid AND agent_id = %s;
                    """,
                    (tenant_id, agent_id),
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
            ok, verify_msg = verify_isolation_state(agent_id, expect_isolated=False)
            st = "verified" if ok else "success"
            msg = f"Network connectivity restore dispatched to endpoint {agent_id}"
            _update_execution(
                execution_id,
                st,
                f"{msg}; {verify_msg}",
                verified=ok,
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

        if body.action_type == "KILL_PROCESS":
            if body.pid is None:
                raise ValueError("pid is required for KILL_PROCESS")
            if not agent_id:
                raise ValueError("Could not resolve endpoint agent for kill")
            ar_cmd = _resolve_ar_command(KILL_AR_COMMAND, WIN_KILL_AR_COMMAND, agent_id)
            # Pass execution_id so AR scripts can POST applied proof to callback_url.
            wazuh_client.run_active_response(
                agent_id=agent_id,
                command=ar_cmd,
                arguments=[str(body.pid), str(execution_id), callback_url],
            )
            shuffle_edr_client.post_edr_workflow(
                {
                    "action": "KILL_PROCESS",
                    "execution_id": execution_id,
                    "callback_url": callback_url,
                    "agent_id": agent_id,
                    "pid": body.pid,
                    "tenant_short_code": body.tenant_short_code,
                    "status": "executing",
                }
            )
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
