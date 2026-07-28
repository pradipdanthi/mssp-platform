"""KB-083: Persist Wazuh enrichment on ingest."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from app.db.session import db_transaction
from app.services.edr_mitre import mitre_from_wazuh_alert

logger = logging.getLogger(__name__)


def bump_telemetry_counter(tenant_id: str, count: int = 1) -> None:
    if count < 1:
        return
    try:
        with db_transaction() as cur:
            cur.execute(
                """
                INSERT INTO edr_telemetry_stats (tenant_id, stat_date, events_processed)
                VALUES (%s::uuid, CURRENT_DATE, %s)
                ON CONFLICT (tenant_id, stat_date)
                DO UPDATE SET events_processed = edr_telemetry_stats.events_processed + EXCLUDED.events_processed;
                """,
                (tenant_id, count),
            )
    except Exception:
        logger.exception("EDR telemetry counter update failed tenant_id=%s", tenant_id)


def persist_wazuh_alert_enrichment(alert_id: str, tenant_id: str, raw: Dict[str, Any]) -> None:
    """Store raw_event + MITRE mapping; count telemetry when process data present."""
    mitre = mitre_from_wazuh_alert(raw)
    try:
        with db_transaction() as cur:
            cur.execute(
                """
                UPDATE security_alerts
                SET raw_event = %s::jsonb,
                    mitre_mapping = %s::jsonb,
                    updated_at = now()
                WHERE id = %s::uuid AND tenant_id = %s::uuid;
                """,
                (json.dumps(raw), json.dumps(mitre), alert_id, tenant_id),
            )
    except Exception:
        logger.exception("Failed persisting Wazuh EDR enrichment alert_id=%s", alert_id)
        return

    blob = json.dumps(raw).lower()
    if "sysmon" in blob or "osquery" in blob or "process" in blob:
        bump_telemetry_counter(tenant_id, 1)
