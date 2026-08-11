"""Kevantic Retrospective Engine — dual-route hunt jobs (appliance vs cloud Data Lake)."""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.db.session import execute, fetch_all, fetch_one
from app.services import cloud_datalake

logger = logging.getLogger(__name__)

ENGINE_LABEL = "Kevantic Retrospective Engine"


def _active_appliance(tenant_id: str) -> Optional[Dict[str, Any]]:
    return fetch_one(
        """
        SELECT
            id::text,
            tenant_id::text,
            appliance_name,
            status,
            host(local_ip) AS ip_address,
            disk_used_gb,
            log_ingest_rate,
            last_seen_at
        FROM appliances
        WHERE tenant_id = %s::uuid
          AND status = 'online'
          AND local_ip IS NOT NULL
        ORDER BY last_seen_at DESC NULLS LAST
        LIMIT 1;
        """,
        (tenant_id,),
    )


def create_hunt_job(
    tenant_id: str,
    iocs: List[Any],
    *,
    lookback_days: int = 90,
    created_by: Optional[str] = None,
    source: str = "threatlens",
) -> Dict[str, Any]:
    """Create PENDING job and choose LOCAL_APPLIANCE vs CLOUD_SOC routing."""
    flat: List[str] = []
    for item in iocs:
        if isinstance(item, dict):
            val = item.get("value") or item.get("ioc_value")
            if val:
                flat.append(str(val).strip())
        elif item:
            flat.append(str(item).strip())
    flat = [x for x in flat if x]
    if not flat:
        raise ValueError("At least one IOC is required")

    appliance = _active_appliance(tenant_id)
    mode = "LOCAL_APPLIANCE" if appliance else "CLOUD_SOC"
    appliance_id = appliance["id"] if appliance else None

    row = fetch_one(
        """
        INSERT INTO retrospective_hunt_jobs (
            tenant_id, appliance_id, execution_mode, status,
            lookback_days, iocs, source, created_by
        )
        VALUES (
            %s::uuid,
            CASE WHEN %s IS NULL THEN NULL ELSE %s::uuid END,
            %s, 'PENDING',
            %s, %s::jsonb, %s,
            CASE WHEN %s IS NULL THEN NULL ELSE %s::uuid END
        )
        RETURNING
            id::text,
            tenant_id::text,
            appliance_id::text,
            execution_mode,
            status,
            lookback_days,
            iocs,
            matches_count,
            matched_details,
            created_at,
            source;
        """,
        (
            tenant_id,
            appliance_id,
            appliance_id,
            mode,
            int(lookback_days),
            json.dumps(flat),
            source,
            created_by,
            created_by,
        ),
    )
    assert row is not None
    return row


def get_job(job_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if tenant_id:
        return fetch_one(
            """
            SELECT
                id::text, tenant_id::text, appliance_id::text,
                execution_mode, status, lookback_days, iocs,
                matches_count, matched_details, error_message, source,
                created_at, started_at, completed_at
            FROM retrospective_hunt_jobs
            WHERE id = %s::uuid AND tenant_id = %s::uuid;
            """,
            (job_id, tenant_id),
        )
    return fetch_one(
        """
        SELECT
            j.id::text, j.tenant_id::text, j.appliance_id::text,
            j.execution_mode, j.status, j.lookback_days, j.iocs,
            j.matches_count, j.matched_details, j.error_message, j.source,
            j.created_at, j.started_at, j.completed_at,
            t.short_code, t.name AS tenant_name
        FROM retrospective_hunt_jobs j
        JOIN tenants t ON t.id = j.tenant_id
        WHERE j.id = %s::uuid;
        """,
        (job_id,),
    )


def list_jobs(
    *,
    tenant_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[List[Dict[str, Any]], int]:
    where = ["TRUE"]
    params: List[Any] = []
    if tenant_id:
        where.append("j.tenant_id = %s::uuid")
        params.append(tenant_id)
    if status:
        where.append("j.status = %s")
        params.append(status.upper())
    where_sql = " AND ".join(where)
    total_row = fetch_one(
        f"SELECT COUNT(*)::int AS n FROM retrospective_hunt_jobs j WHERE {where_sql};",
        tuple(params),
    )
    total = int((total_row or {}).get("n") or 0)
    offset = max(0, (page - 1) * page_size)
    rows = fetch_all(
        f"""
        SELECT
            j.id::text, j.tenant_id::text, j.appliance_id::text,
            j.execution_mode, j.status, j.lookback_days, j.iocs,
            j.matches_count, j.matched_details, j.error_message, j.source,
            j.created_at, j.started_at, j.completed_at,
            t.short_code, t.name AS tenant_name
        FROM retrospective_hunt_jobs j
        JOIN tenants t ON t.id = j.tenant_id
        WHERE {where_sql}
        ORDER BY j.created_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return rows, total


def apply_hunt_result(
    job_id: str,
    *,
    status: str,
    hits: Optional[List[Dict[str, Any]]] = None,
    hit_count: Optional[int] = None,
    error: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Persist appliance/cloud callback results onto the job row."""
    job = get_job(job_id, tenant_id=tenant_id)
    if not job:
        return None
    st = (status or "").upper()
    if st in {"COMPLETE", "DONE", "SUCCESS", "OK"}:
        st = "COMPLETED"
    if st not in {"PENDING", "RUNNING", "COMPLETED", "FAILED"}:
        st = "COMPLETED" if not error else "FAILED"
    details = hits or []
    count = hit_count if hit_count is not None else len(details)
    return fetch_one(
        """
        UPDATE retrospective_hunt_jobs
        SET status = %s,
            matches_count = %s,
            matched_details = %s::jsonb,
            error_message = %s,
            completed_at = CASE
                WHEN %s IN ('COMPLETED', 'FAILED') THEN now()
                ELSE completed_at
            END,
            started_at = COALESCE(started_at, now())
        WHERE id = %s::uuid
        RETURNING
            id::text, tenant_id::text, execution_mode, status,
            matches_count, matched_details, error_message, completed_at;
        """,
        (st, count, json.dumps(details), error, st, job_id),
    )


def enqueue_job_execution(job_id: str) -> None:
    """Execute hunt job (safe to call from FastAPI BackgroundTasks or a thread)."""
    _run_job(job_id)


def spawn_job_execution(job_id: str) -> None:
    """Fire-and-forget worker thread when BackgroundTasks is unavailable."""
    t = threading.Thread(target=_run_job, args=(job_id,), daemon=True, name=f"retro-{job_id[:8]}")
    t.start()


def _run_job(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    execute(
        """
        UPDATE retrospective_hunt_jobs
        SET status = 'RUNNING', started_at = COALESCE(started_at, now())
        WHERE id = %s::uuid AND status IN ('PENDING', 'RUNNING');
        """,
        (job_id,),
    )
    iocs = job.get("iocs") or []
    if isinstance(iocs, str):
        try:
            iocs = json.loads(iocs)
        except json.JSONDecodeError:
            iocs = []
    lookback = int(job.get("lookback_days") or 90)
    try:
        if job["execution_mode"] == "LOCAL_APPLIANCE":
            _dispatch_appliance(job, iocs, lookback)
        else:
            hits = cloud_datalake.search_iocs(
                job["tenant_id"], iocs, lookback_days=lookback
            )
            apply_hunt_result(
                job_id,
                status="COMPLETED",
                hits=hits,
                hit_count=len(hits),
                tenant_id=job["tenant_id"],
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("retrospective job failed job_id=%s", job_id)
        apply_hunt_result(
            job_id,
            status="FAILED",
            hits=[],
            hit_count=0,
            error=str(exc)[:500],
            tenant_id=job["tenant_id"],
        )


def _dispatch_appliance(job: Dict[str, Any], iocs: List[str], lookback: int) -> None:
    """POST hunt to on-prem appliance; results may arrive via /api/v1/telemetry/hunt-results."""
    appliance = fetch_one(
        """
        SELECT id::text, host(local_ip) AS ip_address, status
        FROM appliances WHERE id = %s::uuid;
        """,
        (job.get("appliance_id"),),
    )
    if not appliance or not appliance.get("ip_address"):
        # Fall back to cloud lake if appliance lost
        hits = cloud_datalake.search_iocs(
            job["tenant_id"], iocs, lookback_days=lookback
        )
        apply_hunt_result(
            job["id"],
            status="COMPLETED",
            hits=hits,
            hit_count=len(hits),
            tenant_id=job["tenant_id"],
        )
        return

    port = int(os.getenv("APPLIANCE_HUNT_PORT", "8787"))
    base = os.getenv("APPLIANCE_HUNT_BASE_URL", "").rstrip("/")
    if not base:
        base = f"http://{appliance['ip_address']}:{port}"
    url = f"{base}/appliance/v1/jobs/retrospective-hunt"
    payload = {
        "job_id": job["id"],
        "iocs": iocs,
        "lookback_days": lookback,
        "tenant_id": job["tenant_id"],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "Kevantic-SOC/1.0"},
    )
    timeout = float(os.getenv("APPLIANCE_HUNT_TIMEOUT_SEC", "12"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8") or "{}")
        # Synchronous appliance path may return hits immediately
        if body.get("hits") is not None or body.get("status"):
            apply_hunt_result(
                job["id"],
                status=str(body.get("status") or "COMPLETED"),
                hits=body.get("hits") or [],
                hit_count=body.get("hit_count"),
                error=body.get("error"),
                tenant_id=job["tenant_id"],
            )
        # else leave RUNNING until callback
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning(
            "appliance dispatch deferred job_id=%s err=%s — waiting for callback or mark failed",
            job["id"],
            exc,
        )
        # Keep RUNNING: outbound tunnel / delayed callback is valid for Modes 2/4
        # Soft-fail only when explicitly forced
        if os.getenv("APPLIANCE_HUNT_FAIL_ON_DISPATCH", "").lower() in {"1", "true", "yes"}:
            apply_hunt_result(
                job["id"],
                status="FAILED",
                hits=[],
                hit_count=0,
                error=f"Appliance dispatch failed: {exc}"[:500],
                tenant_id=job["tenant_id"],
            )


def appliance_command_summary() -> Dict[str, Any]:
    """Admin dashboard tile metrics for connected appliances / Data Lake volume."""
    row = fetch_one(
        """
        SELECT
            COUNT(*)::int AS total,
            COUNT(*) FILTER (WHERE status = 'ONLINE')::int AS online,
            COUNT(*) FILTER (WHERE status = 'OFFLINE')::int AS offline,
            COALESCE(SUM(disk_used_gb), 0)::float AS disk_used_gb_total,
            COALESCE(SUM(log_ingest_rate), 0)::float AS log_ingest_rate_total
        FROM tenant_appliances;
        """
    ) or {}
    jobs = fetch_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE status = 'RUNNING')::int AS running,
            COUNT(*) FILTER (WHERE status = 'PENDING')::int AS pending,
            COUNT(*) FILTER (WHERE created_at > now() - interval '24 hours')::int AS last_24h
        FROM retrospective_hunt_jobs;
        """
    ) or {}
    return {
        "engine": ENGINE_LABEL,
        "appliances": {
            "total": int(row.get("total") or 0),
            "online": int(row.get("online") or 0),
            "offline": int(row.get("offline") or 0),
            "disk_used_gb_total": float(row.get("disk_used_gb_total") or 0),
            "log_ingest_rate_total": float(row.get("log_ingest_rate_total") or 0),
        },
        "hunts": {
            "running": int(jobs.get("running") or 0),
            "pending": int(jobs.get("pending") or 0),
            "last_24h": int(jobs.get("last_24h") or 0),
        },
    }


def is_valid_uuid(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except Exception:
        return False
