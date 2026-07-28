"""KB-083: EDR / MXDR API routes (/v1/edr — exposed as /api/v1/edr via nginx)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_current_user, require_tenant_match
from app.db.session import fetch_all, fetch_one
from app.schemas.edr import (
    EdrActionExecuteRequest,
    EdrActionExecuteResponse,
    EdrActionStatusResponse,
    EdrIncidentDeepDiveResponse,
    EdrMetricsSummary,
    MitreMappingPublic,
    ProcessTreeResponse,
)
from app.services.edr_actions import execute_edr_action
from app.services.edr_metrics import (
    endpoint_context_from_events,
    get_edr_metrics,
    load_incident_raw_events,
    merged_mitre_for_incident,
)
from app.services.edr_process_tree import build_process_forest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/edr", tags=["edr-mxdr"])

SOC_ROLES = ("platform_admin", "soc_manager", "soc_analyst")
SOC_CROSS_TENANT = ("platform_admin", "soc_manager", "soc_analyst")


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
    raw_events = []
    if incident_id:
        raw_events = load_incident_raw_events(tenant["id"], incident_id)
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
    tree = build_process_forest(raw_events)
    tree.incident_id = incident_id
    tree.alert_id = alert_id
    return tree


@router.post("/actions/execute", response_model=EdrActionExecuteResponse)
def edr_execute_action(
    body: EdrActionExecuteRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> EdrActionExecuteResponse:
    try:
        execution_id, st, message = execute_edr_action(current_user, body)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return EdrActionExecuteResponse(execution_id=execution_id, status=st, message=message)  # type: ignore[arg-type]


@router.get("/actions/{execution_id}", response_model=EdrActionStatusResponse)
def edr_action_status(
    execution_id: str,
    tenant_short_code: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> EdrActionStatusResponse:
    tenant = _resolve_tenant_for_user(current_user, tenant_short_code)
    row = fetch_one(
        """
        SELECT id::text, action_type, status, result_message,
               created_at::text, updated_at::text
        FROM edr_action_executions
        WHERE id = %s::uuid AND tenant_id = %s::uuid;
        """,
        (execution_id, tenant["id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
    return EdrActionStatusResponse(
        execution_id=row["id"],
        status=row["status"],
        action_type=row["action_type"],
        result_message=row.get("result_message"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


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
    tree = build_process_forest(raw_events)
    tree.incident_id = incident["id"]

    mitre = merged_mitre_for_incident(tenant["id"], incident["id"])
    actions = fetch_all(
        """
        SELECT id::text, action_type, status, result_message,
               created_at::text, updated_at::text
        FROM edr_action_executions
        WHERE tenant_id = %s::uuid AND incident_id = %s::uuid
        ORDER BY created_at DESC LIMIT 20;
        """,
        (tenant["id"], incident["id"]),
    )
    recent = [
        EdrActionStatusResponse(
            execution_id=r["id"],
            status=r["status"],
            action_type=r["action_type"],
            result_message=r.get("result_message"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in actions
    ]
    endpoint = endpoint_context_from_events(raw_events)
    if current_user.get("role") == "customer_viewer":
        endpoint.pop("local_ip", None)

    return EdrIncidentDeepDiveResponse(
        incident_number=incident_number,
        endpoint=endpoint,
        mitre=MitreMappingPublic(**mitre),
        process_tree=tree,
        recent_actions=recent,
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
