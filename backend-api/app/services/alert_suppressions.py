"""Alert suppression matcher: mute matching ingest alerts before incident create."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.services.soc_alert_synthesis import (
    build_alert_evidence,
    extract_wazuh_rule_id,
)

logger = logging.getLogger(__name__)


def _raw_dict(raw_event: Any) -> Dict[str, Any]:
    if isinstance(raw_event, str):
        try:
            raw_event = json.loads(raw_event)
        except (TypeError, ValueError):
            return {}
    return raw_event if isinstance(raw_event, dict) else {}


def _norm(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text.lower() if text else None


def _values_equal(left: Optional[str], right: Optional[str]) -> bool:
    a = _norm(left)
    b = _norm(right)
    if a is None or b is None:
        return False
    return a == b


def extract_match_fields(
    *,
    raw_event: Any = None,
    destination_host: Optional[str] = None,
    rule_id: Optional[str] = None,
    process_path: Optional[str] = None,
    parent_process: Optional[str] = None,
    file_hash: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """
    Normalize match fields from a Wazuh-shaped raw_event with safe fallbacks.

    Returns keys: rule_id, hostname, process_path, parent_process, file_hash,
    process_name (basename of process_path when available).
    """
    raw = _raw_dict(raw_event)
    evidence = build_alert_evidence({"raw_event": raw}) if raw else {}

    rid = (rule_id or "").strip() or extract_wazuh_rule_id(raw) or None
    if not rid and raw.get("rule_id") is not None:
        rid = str(raw.get("rule_id")).strip() or None

    agent = raw.get("agent") if isinstance(raw.get("agent"), dict) else {}
    host = (destination_host or "").strip() or (agent.get("name") or "").strip() or None

    proc = (process_path or "").strip() or evidence.get("process_name")
    parent = (parent_process or "").strip() or evidence.get("parent_process_name")
    fhash = (file_hash or "").strip() or evidence.get("hash_sha256") or evidence.get("hash_md5")
    path = evidence.get("file_path")

    process_name = None
    if proc:
        process_name = proc.replace("\\", "/").rsplit("/", 1)[-1]
    elif evidence.get("process_name"):
        process_name = str(evidence["process_name"]).replace("\\", "/").rsplit("/", 1)[-1]

    return {
        "rule_id": str(rid).strip() if rid else None,
        "hostname": str(host).strip() if host else None,
        "process_path": str(proc).strip() if proc else (str(path).strip() if path else None),
        "parent_process": str(parent).strip() if parent else None,
        "file_hash": str(fhash).strip().lower() if fhash else None,
        "process_name": str(process_name).strip() if process_name else None,
        "path": str(path).strip() if path else None,
    }


def find_matching_suppression(
    cur: Any,
    *,
    tenant_id: str,
    normalized_alert: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Return the most specific active suppression matching this alert, or None.

    Specificity order: host > tenant > global.
    Only compares criteria whose match_* flag is true on the suppression row.
    """
    rule_id = (normalized_alert.get("rule_id") or "").strip()
    if not rule_id:
        return None

    hostname = (normalized_alert.get("hostname") or "").strip() or None
    process_path = normalized_alert.get("process_path")
    parent_process = normalized_alert.get("parent_process")
    file_hash = normalized_alert.get("file_hash")

    cur.execute(
        """
        SELECT
            id::text AS id,
            tenant_id::text AS tenant_id,
            hostname,
            rule_id,
            scope,
            match_process_path,
            process_path_value,
            match_parent_process,
            parent_process_value,
            match_file_hash,
            file_hash_value,
            match_hostname,
            hostname_value,
            expires_at,
            reason,
            created_by_user_id::text AS created_by_user_id,
            created_at,
            disabled_at
        FROM alert_suppressions
        WHERE disabled_at IS NULL
          AND (expires_at IS NULL OR expires_at > now())
          AND rule_id = %s
          AND (
                scope = 'global'
             OR (scope = 'tenant' AND tenant_id = %s::uuid)
             OR (
                    scope = 'host'
                AND tenant_id = %s::uuid
                AND lower(hostname) = lower(%s)
             )
          )
        ORDER BY
            CASE scope
                WHEN 'host' THEN 1
                WHEN 'tenant' THEN 2
                ELSE 3
            END,
            created_at DESC
        LIMIT 50;
        """,
        (rule_id, tenant_id, tenant_id, hostname or ""),
    )
    candidates = list(cur.fetchall() or [])

    for row in candidates:
        if row.get("match_hostname"):
            expected = row.get("hostname_value") or row.get("hostname")
            if not _values_equal(hostname, expected):
                continue
        if row.get("match_process_path"):
            if not _values_equal(process_path, row.get("process_path_value")):
                # Also allow basename match against process_name.
                alert_base = (normalized_alert.get("process_name") or "").strip()
                expected = (row.get("process_path_value") or "").strip()
                expected_base = expected.replace("\\", "/").rsplit("/", 1)[-1]
                if not _values_equal(alert_base, expected) and not _values_equal(
                    alert_base, expected_base
                ):
                    continue
        if row.get("match_parent_process"):
            if not _values_equal(parent_process, row.get("parent_process_value")):
                alert_parent = (parent_process or "").replace("\\", "/").rsplit("/", 1)[-1]
                expected = (row.get("parent_process_value") or "").strip()
                expected_base = expected.replace("\\", "/").rsplit("/", 1)[-1]
                if not _values_equal(alert_parent, expected) and not _values_equal(
                    alert_parent, expected_base
                ):
                    continue
        if row.get("match_file_hash"):
            if not _values_equal(file_hash, row.get("file_hash_value")):
                continue
        return dict(row)

    return None


def apply_suppression_to_alert(
    cur: Any,
    *,
    alert_id: str,
    suppression: Dict[str, Any],
) -> None:
    """Mark alert false_positive / hidden and record an internal audit note on timeline if linked."""
    note = (
        f"Suppressed by rule {suppression.get('id')} "
        f"(scope={suppression.get('scope')} rule_id={suppression.get('rule_id')})"
    )[:4000]
    cur.execute(
        """
        UPDATE security_alerts
        SET status = 'false_positive',
            customer_visible = false,
            updated_at = now(),
            ai_technical_summary = CASE
                WHEN ai_technical_summary IS NULL OR btrim(ai_technical_summary) = ''
                THEN %s
                WHEN ai_technical_summary ILIKE %s THEN ai_technical_summary
                ELSE left(ai_technical_summary || E'\\n' || %s, 4000)
            END
        WHERE id = %s::uuid;
        """,
        (note, f"%{suppression.get('id')}%", note, alert_id),
    )
    logger.info(
        "alert suppressed alert_id=%s suppression_id=%s scope=%s",
        alert_id,
        suppression.get("id"),
        suppression.get("scope"),
    )


def try_suppress_alert(
    cur: Any,
    *,
    tenant_id: str,
    alert_id: str,
    raw_event: Any = None,
    destination_host: Optional[str] = None,
    rule_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    If a suppression matches, apply it and return the suppression row.
    Caller must skip incident creation when this returns a row.
    """
    fields = extract_match_fields(
        raw_event=raw_event,
        destination_host=destination_host,
        rule_id=rule_id,
    )
    match = find_matching_suppression(
        cur, tenant_id=tenant_id, normalized_alert=fields
    )
    if not match:
        return None
    apply_suppression_to_alert(cur, alert_id=alert_id, suppression=match)
    return match
