"""KB-083/084: Persist enrichment + normalized process telemetry on ingest."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.db.session import db_transaction, fetch_one
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


def _extract_agent_fields(raw: Dict[str, Any]) -> Dict[str, Optional[str]]:
    agent = raw.get("agent") if isinstance(raw.get("agent"), dict) else {}
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    win = data.get("win") if isinstance(data.get("win"), dict) else {}
    eventdata = win.get("eventdata") if isinstance(win.get("eventdata"), dict) else {}
    user = None
    for key in ("User", "user", "srcuser", "SubjectUserName"):
        val = eventdata.get(key) or data.get(key)
        if val:
            user = str(val)[:255]
            break
    agent_ip = str(agent.get("ip") or "").strip() or None
    if agent_ip and "/" in agent_ip:
        agent_ip = agent_ip.split("/", 1)[0].strip()
    return {
        "agent_id": str(agent.get("id") or "").strip() or None,
        "agent_name": str(agent.get("name") or "").strip() or None,
        "agent_ip": agent_ip,
        "source_user": user,
    }


def _resolve_asset_id(
    cur: Any,
    tenant_id: str,
    agent_id: Optional[str],
    agent_name: Optional[str],
) -> Optional[str]:
    if agent_id:
        cur.execute(
            """
            SELECT id::text AS id
            FROM protected_assets
            WHERE tenant_id = %s::uuid
              AND details->>'wazuh_agent_id' = %s
            ORDER BY updated_at DESC NULLS LAST, created_at DESC
            LIMIT 1;
            """,
            (tenant_id, agent_id),
        )
        row = cur.fetchone()
        if row:
            return row["id"]
    if agent_name:
        cur.execute(
            """
            SELECT id::text AS id
            FROM protected_assets
            WHERE tenant_id = %s::uuid
              AND lower(hostname) = lower(%s)
            ORDER BY updated_at DESC NULLS LAST, created_at DESC
            LIMIT 1;
            """,
            (tenant_id, agent_name),
        )
        row = cur.fetchone()
        if row:
            return row["id"]
    return None


def _build_technical_summary(raw: Dict[str, Any], fields: Dict[str, Optional[str]]) -> str:
    rule = raw.get("rule") if isinstance(raw.get("rule"), dict) else {}
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    win = data.get("win") if isinstance(data.get("win"), dict) else {}
    eventdata = win.get("eventdata") if isinstance(win.get("eventdata"), dict) else {}
    parts = [
        f"Wazuh rule {rule.get('id', 'n/a')} level {rule.get('level', 'n/a')}",
        str(rule.get("description") or "").strip(),
        (
            f"agent={fields.get('agent_name') or 'n/a'} "
            f"id={fields.get('agent_id') or 'n/a'} "
            f"ip={fields.get('agent_ip') or 'n/a'}"
        ),
    ]
    target = (
        eventdata.get("targetFilename")
        or eventdata.get("TargetFilename")
        or eventdata.get("Image")
    )
    if target:
        parts.append(f"evidence={str(target)[:500]}")
    if fields.get("source_user"):
        parts.append(f"user={fields['source_user']}")
    return "; ".join(p for p in parts if p)[:4000]


def _severity_from_rule(rule: Dict[str, Any]) -> str:
    try:
        level = int(rule.get("level", 10))
    except (TypeError, ValueError):
        level = 10
    if level >= 15:
        return "critical"
    if level >= 10:
        return "high"
    if level >= 7:
        return "medium"
    return "low"


def persist_wazuh_alert_enrichment(alert_id: str, tenant_id: str, raw: Dict[str, Any]) -> None:
    """Store raw_event + MITRE + host/user/asset enrichment for SOC alert detail."""
    rule = raw.get("rule") if isinstance(raw.get("rule"), dict) else {}
    mitre = mitre_from_wazuh_alert(raw)
    fields = _extract_agent_fields(raw)
    norm = normalize_process_event(raw)
    if norm and norm.get("username") and not fields.get("source_user"):
        fields["source_user"] = str(norm["username"])[:255]
    technical = _build_technical_summary(raw, fields)

    from app.services.soc_alert_synthesis import synthesize_soc_guidance

    alert_meta = fetch_one(
        """
        SELECT status, severity, alert_title
        FROM security_alerts
        WHERE id = %s::uuid AND tenant_id = %s::uuid;
        """,
        (alert_id, tenant_id),
    )
    synth_row = {
        "alert_title": str(
            (alert_meta or {}).get("alert_title")
            or rule.get("description")
            or raw.get("title")
            or ""
        ),
        "severity": (alert_meta or {}).get("severity") or _severity_from_rule(rule),
        "status": (alert_meta or {}).get("status") or "new",
        "raw_event": raw,
        "mitre_mapping": mitre,
    }
    synth = synthesize_soc_guidance(synth_row)

    try:
        with db_transaction() as cur:
            asset_id = _resolve_asset_id(
                cur, tenant_id, fields.get("agent_id"), fields.get("agent_name")
            )
            # Prefer asset inventory IP when agent.ip missing.
            dest_ip = fields.get("agent_ip")
            if not dest_ip and asset_id:
                cur.execute(
                    """
                    SELECT host(ip_address)::text AS ip
                    FROM protected_assets
                    WHERE id = %s::uuid AND ip_address IS NOT NULL
                    LIMIT 1;
                    """,
                    (asset_id,),
                )
                ip_row = cur.fetchone()
                if ip_row and ip_row.get("ip"):
                    dest_ip = ip_row["ip"]

            cur.execute(
                """
                UPDATE security_alerts
                SET raw_event = %s::jsonb,
                    mitre_mapping = %s::jsonb,
                    asset_id = COALESCE(asset_id, %s::uuid),
                    source_ip = COALESCE(source_ip, %s::inet),
                    destination_ip = COALESCE(destination_ip, %s::inet),
                    source_user = COALESCE(NULLIF(source_user, ''), %s),
                    destination_host = COALESCE(
                        NULLIF(destination_host, ''), %s
                    ),
                    ai_technical_summary = COALESCE(
                        NULLIF(ai_technical_summary, ''), %s
                    ),
                    ai_likely_attack_type = COALESCE(
                        NULLIF(ai_likely_attack_type, ''), %s
                    ),
                    ai_business_impact = COALESCE(
                        NULLIF(ai_business_impact, ''), %s
                    ),
                    ai_recommended_action = COALESCE(
                        NULLIF(ai_recommended_action, ''), %s
                    ),
                    updated_at = now()
                WHERE id = %s::uuid AND tenant_id = %s::uuid;
                """,
                (
                    json.dumps(raw),
                    json.dumps(mitre),
                    asset_id,
                    dest_ip,
                    dest_ip,
                    fields.get("source_user"),
                    fields.get("agent_name"),
                    technical,
                    synth["likely_attack_type"],
                    synth["business_impact"],
                    synth["recommended_action"],
                    alert_id,
                    tenant_id,
                ),
            )
            from app.services.alert_parser import persist_alert_telemetry

            persist_alert_telemetry(
                cur,
                alert_id=alert_id,
                tenant_id=tenant_id,
                raw=raw,
                alert_description=str((alert_meta or {}).get("alert_title") or ""),
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
