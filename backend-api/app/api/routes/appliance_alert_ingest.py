"""KB-057 customer-safe, normalized alert ingestion from appliances."""

import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Response, status

from app.db.session import db_transaction
from app.schemas.alert_ingest import (
    ApplianceAlertIngestRequest,
    ApplianceAlertIngestResponse,
)
from app.services.appliance_auth_service import (
    ApplianceRetiredError,
    InvalidApplianceCredentialsError,
    verify_appliance_credentials,
)
from app.services.endpoint_asset_resolve import (
    agent_stub_raw_event,
    resolve_endpoint_asset,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/appliance", tags=["appliance-alert-ingest"])


@router.post(
    "/alerts",
    response_model=ApplianceAlertIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_appliance_alert(
    payload: ApplianceAlertIngestRequest,
    response: Response,
    x_appliance_id: Optional[str] = Header(default=None, alias="X-Appliance-ID"),
    x_appliance_api_key: Optional[str] = Header(default=None, alias="X-Appliance-API-Key"),
) -> Dict[str, Any]:
    """Authenticate an appliance and store one tenant-scoped safe alert."""
    if not x_appliance_id or not x_appliance_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing appliance credentials",
        )

    try:
        appliance_id = str(UUID(x_appliance_id))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid appliance credentials",
        )

    try:
        appliance = verify_appliance_credentials(appliance_id, x_appliance_api_key)
    except InvalidApplianceCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid appliance credentials",
        )
    except ApplianceRetiredError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Appliance is retired and cannot ingest alerts",
        )
    except Exception:
        logger.exception("Unexpected error while authenticating appliance alert ingest")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Alert could not be ingested due to an internal error",
        )

    incident_id = None
    incident_number = None
    try:
        with db_transaction() as cur:
            # No schema change is allowed in KB-057. A transaction-scoped
            # advisory lock serializes concurrent submissions for this
            # tenant/source/external-id tuple before the duplicate lookup.
            duplicate_key = (
                f"{appliance['tenant_id']}:{payload.source_tool}:"
                f"{payload.external_alert_id}"
            )
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0));",
                (duplicate_key,),
            )
            cur.execute(
                """
                SELECT id::text, customer_visible, status
                FROM security_alerts
                WHERE tenant_id = %s
                  AND source_tool = %s
                  AND external_alert_id = %s
                ORDER BY created_at
                LIMIT 1;
                """,
                (
                    appliance["tenant_id"],
                    payload.source_tool,
                    payload.external_alert_id,
                ),
            )
            alert_row = cur.fetchone()

            if alert_row:
                response.status_code = status.HTTP_200_OK
                duplicate = True
            else:
                linked = resolve_endpoint_asset(
                    str(appliance["tenant_id"]),
                    hostname=payload.destination_host,
                    alert_description=payload.alert_description,
                    cur=cur,
                )
                dest_host = payload.destination_host or (linked or {}).get("hostname")
                raw_stub = agent_stub_raw_event(linked)
                incoming_raw = payload.raw_event or {}
                if not isinstance(incoming_raw, dict):
                    incoming_raw = {}
                merged_raw = dict(incoming_raw)
                if raw_stub:
                    merged_raw.setdefault("asset_stub", raw_stub)
                # Optional appliance-local AI fields (absent on older appliances — OK).
                existing_ai = merged_raw.get("appliance_ai")
                ai_block = dict(existing_ai) if isinstance(existing_ai, dict) else {}
                if payload.appliance_ai_verdict:
                    ai_block["verdict"] = payload.appliance_ai_verdict
                if payload.appliance_ai_confidence is not None:
                    ai_block["confidence"] = payload.appliance_ai_confidence
                if payload.appliance_ai_summary:
                    ai_block["summary"] = payload.appliance_ai_summary
                if ai_block:
                    merged_raw["appliance_ai"] = ai_block
                cur.execute(
                    """
                    INSERT INTO security_alerts (
                        tenant_id, appliance_id, source_tool, external_alert_id,
                        severity, alert_title, alert_description, event_time,
                        destination_host, source_ip, destination_ip, source_user,
                        asset_id, raw_event, mitre_mapping, customer_visible, status
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, COALESCE(%s, now()),
                        %s, %s::inet, %s::inet, %s,
                        %s::uuid, %s::jsonb, %s::jsonb, true, 'new'
                    )
                    RETURNING id::text, customer_visible, status;
                    """,
                    # Appliance cannot choose visibility. Server publishes
                    # customer-safe rows; SOC can later set false for noise.
                    (
                        appliance["tenant_id"],
                        appliance["id"],
                        payload.source_tool,
                        payload.external_alert_id,
                        payload.severity,
                        payload.alert_title,
                        payload.alert_description,
                        payload.event_time,
                        dest_host,
                        payload.source_ip,
                        payload.destination_ip,
                        payload.source_user,
                        (linked or {}).get("id"),
                        json.dumps(merged_raw),
                        json.dumps(payload.mitre_mapping or {}),
                    ),
                )
                alert_row = cur.fetchone()
                duplicate = False

                from app.services.alert_parser import persist_alert_telemetry

                persist_alert_telemetry(
                    cur,
                    alert_id=alert_row["id"],
                    tenant_id=str(appliance["tenant_id"]),
                    raw=merged_raw,
                    alert_description=payload.alert_description or "",
                )

                from app.services.alert_suppressions import try_suppress_alert

                suppressed = try_suppress_alert(
                    cur,
                    tenant_id=str(appliance["tenant_id"]),
                    alert_id=alert_row["id"],
                    raw_event=merged_raw,
                    destination_host=dest_host,
                )
                if suppressed:
                    cur.execute(
                        """
                        SELECT id::text, customer_visible, status
                        FROM security_alerts WHERE id = %s::uuid;
                        """,
                        (alert_row["id"],),
                    )
                    alert_row = cur.fetchone() or alert_row
                else:
                    cur.execute(
                        "SELECT short_code FROM tenants WHERE id = %s::uuid;",
                        (appliance["tenant_id"],),
                    )
                    tenant_row = cur.fetchone() or {}
                    short_code = str(tenant_row.get("short_code") or "TENANT")
                    from app.services.appliance_alert_incidents import (
                        ensure_incident_for_appliance_alert,
                    )

                    incident = ensure_incident_for_appliance_alert(
                        cur,
                        tenant_id=str(appliance["tenant_id"]),
                        short_code=short_code,
                        alert_id=alert_row["id"],
                        severity=payload.severity,
                        alert_title=payload.alert_title,
                        destination_host=dest_host,
                    )
                    if incident:
                        incident_id, incident_number = incident
                        cur.execute(
                            """
                            SELECT id::text, customer_visible, status
                            FROM security_alerts WHERE id = %s::uuid;
                            """,
                            (alert_row["id"],),
                        )
                        alert_row = cur.fetchone() or alert_row

            cur.execute(
                """
                UPDATE appliances
                SET appliance_key_last_used_at = now()
                WHERE id = %s;
                """,
                (appliance["id"],),
            )
    except Exception:
        logger.exception("Unexpected error while storing normalized appliance alert")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Alert could not be ingested due to an internal error",
        )

    out: Dict[str, Any] = {
        "alert_id": alert_row["id"],
        "duplicate": duplicate,
        "customer_visible": alert_row["customer_visible"],
        "status": alert_row["status"],
        "message": "Alert already received" if duplicate else "Alert received for SOC triage",
    }
    if incident_id and incident_number:
        out["incident_id"] = incident_id
        out["incident_number"] = incident_number

    # KB-092: enqueue new high/critical appliance alerts for LLM fill (no-op if disabled).
    if not duplicate:
        try:
            from app.services.ai_alert_queue import enqueue_ai_alert_analysis

            enqueue_ai_alert_analysis(
                alert_id=str(alert_row["id"]),
                tenant_id=str(appliance["tenant_id"]),
                severity=payload.severity,
            )
        except Exception:  # noqa: BLE001
            logger.exception("AI alert enqueue failed for alert_id=%s", alert_row["id"])

    return out
