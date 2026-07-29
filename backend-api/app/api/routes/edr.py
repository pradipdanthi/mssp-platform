"""KB-083/084: EDR / MXDR API routes (/v1/edr — exposed as /api/v1/edr via nginx)."""

from __future__ import annotations

import hmac
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from app.api.dependencies import get_current_user, require_tenant_match
from app.db.session import db_transaction, fetch_all, fetch_one
from app.schemas.edr import (
    EdrActionCallbackRequest,
    EdrActionExecuteRequest,
    EdrActionExecuteResponse,
    EdrActionStatusResponse,
    EdrForensicsCompleteRequest,
    EdrIncidentDeepDiveResponse,
    EdrMetricsSummary,
    ForensicArtifactPublic,
    MitreMappingPublic,
    ProcessTreeResponse,
)
from app.services import edr_forensics_storage
from app.services.edr_actions import apply_action_callback, execute_edr_action, normalize_status
from app.services.edr_metrics import (
    endpoint_context_from_events,
    get_edr_metrics,
    load_incident_raw_events,
    merged_mitre_for_incident,
)
from app.services.edr_process_tree import build_process_forest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/edr", tags=["edr-mxdr"])

SOC_CROSS_TENANT = ("platform_admin", "soc_manager", "soc_analyst")


def _read_secret_file(*candidates: str) -> str:
    for candidate in candidates:
        try:
            value = Path(candidate).read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            continue
    return ""


def _edr_callback_key() -> str:
    env = (os.getenv("EDR_CALLBACK_API_KEY") or "").strip()
    if env:
        return env
    key_file = (os.getenv("EDR_CALLBACK_API_KEY_FILE") or "").strip()
    if key_file:
        try:
            return Path(key_file).read_text(encoding="utf-8").strip()
        except OSError:
            pass
    direct = (os.getenv("SOC_SYNC_API_KEY") or "").strip()
    if direct:
        return direct
    return _read_secret_file(
        "/run/secrets/soc_sync_api_key",
        "/opt/mssp-control/.secrets/soc_sync_api_key",
        "/run/secrets/edr_callback_api_key",
        "/opt/mssp-control/.secrets/edr_callback_api_key",
    )


def _require_callback_auth(
    x_edr_callback_key: Optional[str],
    x_soc_sync_key: Optional[str],
) -> None:
    expected = _edr_callback_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EDR callback authentication is not configured",
        )
    provided = (x_edr_callback_key or x_soc_sync_key or "").strip()
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def _resolve_tenant_for_user(user: Dict[str, Any], short_code: Optional[str]) -> Dict[str, Any]:
    if user.get("role") in SOC_CROSS_TENANT:
        if not short_code:
            raise HTTPException(status_code=400, detail="tenant_short_code is required")
        code = short_code.upper()
    else:
        if not short_code:
            tenant_id = user.get("tenant_id")
            row = fetch_one(
                "SELECT id::text, short_code FROM tenants WHERE id = %s::uuid;",
                (tenant_id,),
            )
            if not row:
                raise HTTPException(status_code=404, detail="Tenant not found")
            require_tenant_match(row["id"], user)
            return row
        code = short_code.upper()

    tenant = fetch_one(
        "SELECT id::text, short_code FROM tenants WHERE short_code = %s;",
        (code,),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    require_tenant_match(tenant["id"], user)
    return tenant


def _action_status_response(row: Dict[str, Any]) -> EdrActionStatusResponse:
    download_url = None
    artifact_id = None
    if row.get("action_type") == "COLLECT_FORENSICS":
        art = fetch_one(
            """
            SELECT id::text, tenant_id::text, status
            FROM edr_forensic_artifacts
            WHERE execution_id = %s::uuid
            ORDER BY created_at DESC LIMIT 1;
            """,
            (row["id"],),
        )
        if art:
            artifact_id = art["id"]
            if art.get("status") == "uploaded":
                download_url = edr_forensics_storage.build_download_url(
                    artifact_id=art["id"], tenant_id=art["tenant_id"]
                )["download_url"]
    return EdrActionStatusResponse(
        execution_id=row["id"],
        status=normalize_status(row["status"]),  # type: ignore[arg-type]
        action_type=row["action_type"],
        result_message=row.get("result_message"),
        status_detail=row.get("status_detail"),
        verified_at=row.get("verified_at"),
        download_url=download_url,
        forensic_artifact_id=artifact_id,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("/telemetry/process-tree", response_model=ProcessTreeResponse)
def edr_process_tree(
    incident_id: Optional[str] = Query(default=None),
    alert_id: Optional[str] = Query(default=None),
    tenant_short_code: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ProcessTreeResponse:
    if not incident_id and not alert_id:
        raise HTTPException(status_code=400, detail="incident_id or alert_id is required")
    tenant = _resolve_tenant_for_user(current_user, tenant_short_code)
    raw_events: list = []
    normalized_rows: list = []
    if incident_id:
        raw_events = load_incident_raw_events(tenant["id"], incident_id)
        normalized_rows = fetch_all(
            """
            SELECT pid, parent_pid, process_guid, parent_process_guid,
                   process_name, parent_process_name, command_line, parent_command_line,
                   username, hash_md5, hash_sha256, signed_status, event_time,
                   mitre_techniques
            FROM edr_process_events
            WHERE tenant_id = %s::uuid
              AND alert_id IN (
                SELECT alert_id FROM incident_alerts WHERE incident_id = %s::uuid
                UNION
                SELECT primary_alert_id FROM incidents WHERE id = %s::uuid
              );
            """,
            (tenant["id"], incident_id, incident_id),
        )
    elif alert_id:
        row = fetch_one(
            """
            SELECT raw_event FROM security_alerts
            WHERE id = %s::uuid AND tenant_id = %s::uuid;
            """,
            (alert_id, tenant["id"]),
        )
        if row and isinstance(row.get("raw_event"), dict):
            raw_events = [row["raw_event"]]
        normalized_rows = fetch_all(
            """
            SELECT pid, parent_pid, process_guid, parent_process_guid,
                   process_name, parent_process_name, command_line, parent_command_line,
                   username, hash_md5, hash_sha256, signed_status, event_time,
                   mitre_techniques
            FROM edr_process_events
            WHERE tenant_id = %s::uuid AND alert_id = %s::uuid;
            """,
            (tenant["id"], alert_id),
        )
    tree = build_process_forest(raw_events, normalized_rows=normalized_rows or None)
    tree.incident_id = incident_id
    tree.alert_id = alert_id
    return tree


@router.post("/actions/execute", response_model=EdrActionExecuteResponse)
async def edr_execute_action(
    body: EdrActionExecuteRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> EdrActionExecuteResponse:
    import asyncio
    try:
        execution_id, st, message, upload_url, artifact_id = await asyncio.to_thread(
            execute_edr_action, current_user, body
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return EdrActionExecuteResponse(
        execution_id=execution_id,
        status=st,  # type: ignore[arg-type]
        message=message,
        upload_url=upload_url,
        forensic_artifact_id=artifact_id,
    )


@router.post("/actions/callback")
def edr_action_callback(
    body: EdrActionCallbackRequest,
    x_edr_callback_key: Optional[str] = Header(default=None, alias="X-EDR-Callback-Key"),
    x_soc_sync_key: Optional[str] = Header(default=None, alias="X-SOC-Sync-Key"),
) -> Dict[str, Any]:
    _require_callback_auth(x_edr_callback_key, x_soc_sync_key)
    try:
        return apply_action_callback(
            execution_id=body.execution_id,
            status=body.status,
            message=body.message,
            error_log=body.error_log,
            agent_id=body.agent_id,
            external_ref=body.external_ref,
            payload=body.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/actions/{execution_id}", response_model=EdrActionStatusResponse)
def edr_action_status(
    execution_id: str,
    tenant_short_code: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> EdrActionStatusResponse:
    tenant = _resolve_tenant_for_user(current_user, tenant_short_code)
    row = fetch_one(
        """
        SELECT id::text, action_type, status, result_message, status_detail,
               verified_at::text, created_at::text, updated_at::text
        FROM edr_action_executions
        WHERE id = %s::uuid AND tenant_id = %s::uuid;
        """,
        (execution_id, tenant["id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
    return _action_status_response(row)


@router.put("/forensics/upload/{artifact_id}")
async def edr_forensics_upload(
    artifact_id: str,
    request: Request,
    token: str = Query(...),
) -> Dict[str, Any]:
    row = fetch_one(
        """
        SELECT id::text, tenant_id::text, object_key, status
        FROM edr_forensic_artifacts
        WHERE id = %s::uuid;
        """,
        (artifact_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if not edr_forensics_storage.verify_signed_token(
        token=token,
        artifact_id=artifact_id,
        tenant_id=row["tenant_id"],
        purpose="upload",
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired upload token")
    max_bytes = int(os.getenv("EDR_FORENSICS_MAX_BYTES") or str(512 * 1024 * 1024))
    try:
        size, sha = await edr_forensics_storage.write_upload_stream(
            object_key=row["object_key"],
            stream=request.stream(),
            max_bytes=max_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    if size == 0:
        raise HTTPException(status_code=400, detail="Empty upload body")
    with db_transaction() as cur:
        cur.execute(
            """
            UPDATE edr_forensic_artifacts
            SET status = 'uploaded',
                file_size_bytes = %s,
                sha256 = %s,
                file_name = COALESCE(file_name, 'triage.zip'),
                updated_at = now()
            WHERE id = %s::uuid;
            """,
            (size, sha, artifact_id),
        )
        cur.execute(
            """
            UPDATE edr_action_executions
            SET status = 'success',
                result_message = %s,
                updated_at = now()
            WHERE id = (
                SELECT execution_id FROM edr_forensic_artifacts WHERE id = %s::uuid
            );
            """,
            (f"Forensic package uploaded ({size} bytes)", artifact_id),
        )
    return {
        "artifact_id": artifact_id,
        "status": "uploaded",
        "file_size_bytes": size,
        "sha256": sha,
    }


@router.get("/forensics/download/{artifact_id}")
def edr_forensics_download(
    artifact_id: str,
    token: str = Query(...),
) -> Response:
    row = fetch_one(
        """
        SELECT id::text, tenant_id::text, object_key, status, file_name, content_type
        FROM edr_forensic_artifacts
        WHERE id = %s::uuid;
        """,
        (artifact_id,),
    )
    if not row or row.get("status") != "uploaded":
        raise HTTPException(status_code=404, detail="Artifact not found")
    if not edr_forensics_storage.verify_signed_token(
        token=token,
        artifact_id=artifact_id,
        tenant_id=row["tenant_id"],
        purpose="download",
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired download token")
    try:
        data = edr_forensics_storage.read_download(object_key=row["object_key"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact file missing")
    filename = row.get("file_name") or "triage.zip"
    return Response(
        content=data,
        media_type=row.get("content_type") or "application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/forensics/complete")
def edr_forensics_complete(
    body: EdrForensicsCompleteRequest,
    x_edr_callback_key: Optional[str] = Header(default=None, alias="X-EDR-Callback-Key"),
    x_soc_sync_key: Optional[str] = Header(default=None, alias="X-SOC-Sync-Key"),
) -> Dict[str, Any]:
    _require_callback_auth(x_edr_callback_key, x_soc_sync_key)
    row = None
    if body.artifact_id:
        row = fetch_one(
            """
            SELECT id::text, tenant_id::text, execution_id::text, object_key, status
            FROM edr_forensic_artifacts WHERE id = %s::uuid;
            """,
            (body.artifact_id,),
        )
    elif body.execution_id:
        row = fetch_one(
            """
            SELECT id::text, tenant_id::text, execution_id::text, object_key, status
            FROM edr_forensic_artifacts
            WHERE execution_id = %s::uuid
            ORDER BY created_at DESC LIMIT 1;
            """,
            (body.execution_id,),
        )
    if not row:
        raise HTTPException(status_code=404, detail="Forensic artifact not found")

    if body.tenant_id and str(body.tenant_id) != str(row["tenant_id"]):
        raise HTTPException(status_code=404, detail="Forensic artifact not found")
    if body.tenant_short_code:
        tenant = fetch_one(
            "SELECT id::text FROM tenants WHERE short_code = %s;",
            (body.tenant_short_code.upper(),),
        )
        if not tenant or tenant["id"] != row["tenant_id"]:
            raise HTTPException(status_code=404, detail="Forensic artifact not found")

    new_status = body.status
    with db_transaction() as cur:
        cur.execute(
            """
            UPDATE edr_forensic_artifacts
            SET status = %s,
                file_size_bytes = COALESCE(%s, file_size_bytes),
                sha256 = COALESCE(%s, sha256),
                object_key = COALESCE(%s, object_key),
                agent_id = COALESCE(%s, agent_id),
                updated_at = now()
            WHERE id = %s::uuid;
            """,
            (
                new_status,
                body.file_size_bytes,
                body.sha256,
                body.object_key,
                body.endpoint_id,
                row["id"],
            ),
        )
        if row.get("execution_id"):
            exec_status = "success" if new_status == "uploaded" else "failed"
            cur.execute(
                """
                UPDATE edr_action_executions
                SET status = %s,
                    result_message = %s,
                    updated_at = now()
                WHERE id = %s::uuid;
                """,
                (
                    exec_status,
                    (body.message or f"Forensics {new_status}")[:2000],
                    row["execution_id"],
                ),
            )
    download = None
    if new_status == "uploaded":
        download = edr_forensics_storage.build_download_url(
            artifact_id=row["id"], tenant_id=row["tenant_id"]
        )["download_url"]
    return {
        "artifact_id": row["id"],
        "status": new_status,
        "download_url": download,
    }


@router.get("/incidents/deep-dive", response_model=EdrIncidentDeepDiveResponse)
def edr_incident_deep_dive(
    incident_number: str = Query(..., min_length=3),
    tenant_short_code: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> EdrIncidentDeepDiveResponse:
    tenant = _resolve_tenant_for_user(current_user, tenant_short_code)
    incident = fetch_one(
        """
        SELECT id::text AS id, incident_number
        FROM incidents
        WHERE tenant_id = %s::uuid AND incident_number = %s;
        """,
        (tenant["id"], incident_number),
    )
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    raw_events = load_incident_raw_events(tenant["id"], incident["id"])
    normalized_rows = fetch_all(
        """
        SELECT pid, parent_pid, process_guid, parent_process_guid,
               process_name, parent_process_name, command_line, parent_command_line,
               username, hash_md5, hash_sha256, signed_status, event_time,
               mitre_techniques
        FROM edr_process_events
        WHERE tenant_id = %s::uuid
          AND alert_id IN (
            SELECT alert_id FROM incident_alerts WHERE incident_id = %s::uuid
            UNION
            SELECT primary_alert_id FROM incidents WHERE id = %s::uuid
          );
        """,
        (tenant["id"], incident["id"], incident["id"]),
    )
    tree = build_process_forest(raw_events, normalized_rows=normalized_rows or None)
    tree.incident_id = incident["id"]

    mitre = merged_mitre_for_incident(tenant["id"], incident["id"])
    actions = fetch_all(
        """
        SELECT id::text, action_type, status, result_message, status_detail,
               verified_at::text, created_at::text, updated_at::text
        FROM edr_action_executions
        WHERE tenant_id = %s::uuid AND incident_id = %s::uuid
        ORDER BY created_at DESC LIMIT 20;
        """,
        (tenant["id"], incident["id"]),
    )
    recent = [_action_status_response(r) for r in actions]
    artifacts = fetch_all(
        """
        SELECT id::text, status, file_name, file_size_bytes, sha256, created_at::text,
               tenant_id::text
        FROM edr_forensic_artifacts
        WHERE tenant_id = %s::uuid
          AND execution_id IN (
            SELECT id FROM edr_action_executions
            WHERE tenant_id = %s::uuid AND incident_id = %s::uuid
          )
        ORDER BY created_at DESC LIMIT 10;
        """,
        (tenant["id"], tenant["id"], incident["id"]),
    )
    forensic_public = []
    for a in artifacts:
        dl = None
        if a.get("status") == "uploaded":
            dl = edr_forensics_storage.build_download_url(
                artifact_id=a["id"], tenant_id=a["tenant_id"]
            )["download_url"]
        forensic_public.append(
            ForensicArtifactPublic(
                artifact_id=a["id"],
                status=a["status"],
                file_name=a.get("file_name"),
                file_size_bytes=a.get("file_size_bytes"),
                sha256=a.get("sha256"),
                download_url=dl,
                created_at=a["created_at"],
            )
        )
    endpoint = endpoint_context_from_events(raw_events)
    if current_user.get("role") == "customer_viewer":
        endpoint.pop("local_ip", None)

    return EdrIncidentDeepDiveResponse(
        incident_number=incident_number,
        endpoint=endpoint,
        mitre=MitreMappingPublic(**mitre),
        process_tree=tree,
        recent_actions=recent,
        forensic_artifacts=forensic_public,
    )


@router.get("/metrics/summary", response_model=EdrMetricsSummary)
def edr_metrics_summary(
    tenant_short_code: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> EdrMetricsSummary:
    tenant_id: Optional[str] = None
    if tenant_short_code or current_user.get("role") not in SOC_CROSS_TENANT:
        tenant = _resolve_tenant_for_user(current_user, tenant_short_code)
        tenant_id = tenant["id"]
    return get_edr_metrics(tenant_id=tenant_id)
