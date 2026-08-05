"""Cloud→appliance job queue (Phase A: pull via heartbeat)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.db.session import db_transaction, fetch_all, fetch_one

logger = logging.getLogger(__name__)


def enqueue_job(
    *,
    appliance_id: str,
    tenant_id: str,
    job_type: str,
    payload: Dict[str, Any],
    edr_execution_id: Optional[str] = None,
    requested_by_user_id: Optional[str] = None,
    expires_hours: int = 24,
) -> Dict[str, Any]:
    with db_transaction() as cur:
        cur.execute(
            """
            INSERT INTO appliance_jobs (
                appliance_id, tenant_id, job_type, payload,
                edr_execution_id, requested_by_user_id, expires_at
            )
            VALUES (
                %s::uuid, %s::uuid, %s, %s::jsonb,
                %s::uuid, %s::uuid, now() + (%s || ' hours')::interval
            )
            RETURNING id::text, status, created_at::text;
            """,
            (
                appliance_id,
                tenant_id,
                job_type,
                json.dumps(payload),
                edr_execution_id,
                requested_by_user_id,
                str(int(expires_hours)),
            ),
        )
        row = cur.fetchone()
    return dict(row)


def list_pending_jobs(appliance_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        UPDATE appliance_jobs
        SET status = 'dispatched',
            dispatched_at = COALESCE(dispatched_at, now()),
            updated_at = now()
        WHERE id IN (
            SELECT id FROM appliance_jobs
            WHERE appliance_id = %s::uuid
              AND status = 'pending'
              AND expires_at > now()
            ORDER BY created_at ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id::text, job_type, payload, edr_execution_id::text,
                  created_at::text, expires_at::text;
        """,
        (appliance_id, limit),
    )
    # fetch_all may not work with UPDATE RETURNING depending on session helper —
    # use transaction path if empty unexpected. Fall back:
    if rows is None:
        rows = []
    out = []
    for r in rows:
        item = dict(r)
        if isinstance(item.get("payload"), str):
            try:
                item["payload"] = json.loads(item["payload"])
            except Exception:
                item["payload"] = {}
        out.append(item)
    return out


def claim_pending_jobs(appliance_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    """Mark pending jobs dispatched and return them for the appliance."""
    with db_transaction() as cur:
        cur.execute(
            """
            SELECT id FROM appliance_jobs
            WHERE appliance_id = %s::uuid
              AND status = 'pending'
              AND expires_at > now()
            ORDER BY created_at ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED;
            """,
            (appliance_id, limit),
        )
        ids = [str(r["id"]) for r in (cur.fetchall() or [])]
        if not ids:
            return []
        cur.execute(
            """
            UPDATE appliance_jobs
            SET status = 'dispatched',
                dispatched_at = COALESCE(dispatched_at, now()),
                updated_at = now()
            WHERE id = ANY(%s::uuid[])
            RETURNING id::text, job_type, payload, edr_execution_id::text,
                      created_at::text, expires_at::text;
            """,
            (ids,),
        )
        rows = cur.fetchall() or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        payload = item.get("payload")
        if isinstance(payload, str):
            try:
                item["payload"] = json.loads(payload)
            except Exception:
                item["payload"] = {}
        out.append(item)
    return out


def complete_job(
    *,
    job_id: str,
    appliance_id: str,
    success: bool,
    result: Optional[Dict[str, Any]] = None,
    message: str = "",
) -> Optional[Dict[str, Any]]:
    status = "success" if success else "failed"
    result_body = dict(result or {})
    if message:
        result_body["message"] = message
    with db_transaction() as cur:
        cur.execute(
            """
            UPDATE appliance_jobs
            SET status = %s,
                result = %s::jsonb,
                completed_at = now(),
                updated_at = now()
            WHERE id = %s::uuid
              AND appliance_id = %s::uuid
              AND status IN ('pending', 'dispatched', 'executing')
            RETURNING id::text, edr_execution_id::text, job_type, tenant_id::text, payload;
            """,
            (status, json.dumps(result_body), job_id, appliance_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def expire_stale_jobs() -> int:
    with db_transaction() as cur:
        cur.execute(
            """
            UPDATE appliance_jobs
            SET status = 'expired', updated_at = now(), completed_at = now()
            WHERE status IN ('pending', 'dispatched')
              AND expires_at <= now()
            RETURNING id;
            """
        )
        return len(cur.fetchall() or [])
