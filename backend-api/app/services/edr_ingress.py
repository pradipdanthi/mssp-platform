"""KB-083/084: Persist enrichment + normalized process telemetry on ingest."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from app.db.session import db_transaction
from app.services.edr_mitre import mitre_from_wazuh_alert
from app.services.edr_process_tree import normalize_process_event

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


def _persist_process_event(alert_id: str, tenant_id: str, raw: Dict[str, Any]) -> bool:
    norm = normalize_process_event(raw)
    if not norm:
        return False
    try:
        with db_transaction() as cur:
            cur.execute(
                """
                INSERT INTO edr_process_events (
                    tenant_id, alert_id, agent_id,
                    pid, parent_pid, process_guid, parent_process_guid,
                    process_name, parent_process_name, command_line, parent_command_line,
                    username, hash_md5, hash_sha256, signed_status, event_time,
                    mitre_techniques, raw_source
                )
                VALUES (
                    %s::uuid, %s::uuid, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s::jsonb, %s
                );
                """,
                (
                    tenant_id,
                    alert_id,
                    norm.get("agent_id"),
                    norm.get("pid"),
                    norm.get("parent_pid"),
                    norm.get("process_guid"),
                    norm.get("parent_process_guid"),
                    norm.get("process_name"),
                    norm.get("parent_process_name"),
                    norm.get("command_line"),
                    norm.get("parent_command_line"),
                    norm.get("username"),
                    norm.get("hash_md5"),
                    norm.get("hash_sha256"),
                    norm.get("signed_status"),
                    norm.get("event_time"),
                    json.dumps(norm.get("mitre_techniques") or []),
                    norm.get("raw_source"),
                ),
            )
        return True
    except Exception:
        logger.exception("Failed persisting process event alert_id=%s", alert_id)
        return False


def persist_wazuh_alert_enrichment(alert_id: str, tenant_id: str, raw: Dict[str, Any]) -> None:
    """Store raw_event + MITRE mapping; normalize process telemetry when present."""
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

    if _persist_process_event(alert_id, tenant_id, raw):
        bump_telemetry_counter(tenant_id, 1)
        return

    blob = json.dumps(raw).lower()
    if "sysmon" in blob or "osquery" in blob or "process" in blob or "audit" in blob:
        bump_telemetry_counter(tenant_id, 1)
