"""KB-057 customer-safe, normalized alert ingestion from appliances."""

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
                cur.execute(
                    """
                    INSERT INTO security_alerts (
                        tenant_id, appliance_id, source_tool, external_alert_id,
                        severity, alert_title, alert_description, event_time,
                        destination_host, customer_visible, status
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, COALESCE(%s, now()),
                        %s, false, 'new'
                    )
                    RETURNING id::text, customer_visible, status;
                    """,
                    (
                        appliance["tenant_id"],
                        appliance["id"],
                        payload.source_tool,
                        payload.external_alert_id,
                        payload.severity,
                        payload.alert_title,
                        payload.alert_description,
                        payload.event_time,
                        payload.destination_host,
                    ),
                )
                alert_row = cur.fetchone()
                duplicate = False

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
                    destination_host=payload.destination_host,
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
