"""
Phase 5: Asynchronous batched archival of aged security alerts before purge.

Exports compressed JSONL per tenant/batch under LOG_ARCHIVE_DIR, then deletes
archived rows in bounded batches to avoid long locks.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.db.session import execute, fetch_all

logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE_DIR = "/var/lib/mssp/log-archive"
DEFAULT_BATCH_SIZE = 1000
ARCHIVER_INTERVAL_SECONDS = int(os.getenv("LOG_ARCHIVER_INTERVAL_SECONDS", str(6 * 3600)))

_worker_started = False
_lock = threading.Lock()


def _archive_root() -> Path:
    root = Path(os.getenv("LOG_ARCHIVE_DIR", DEFAULT_ARCHIVE_DIR))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _export_batch_jsonl_gz(
    *,
    tenant_id: str,
    rows: List[Dict[str, Any]],
    archive_day: str,
    batch_index: int,
) -> Path:
    tenant_dir = _archive_root() / tenant_id / archive_day
    tenant_dir.mkdir(parents=True, exist_ok=True)
    out_path = tenant_dir / f"security_alerts_batch_{batch_index:05d}.jsonl.gz"
    with gzip.open(out_path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str))
            handle.write("\n")
    return out_path


def archive_old_tenant_logs(
    days_old: int = 30,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Dict[str, Any]:
    """
    Export security alerts older than ``days_old`` to compressed JSONL, then delete them.

    Returns summary counters; safe to run repeatedly (idempotent per batch).
    """
    days_old = max(1, int(days_old))
    batch_size = max(100, min(int(batch_size), 5000))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
    archive_day = cutoff.date().isoformat()

    summary: Dict[str, Any] = {
        "cutoff": cutoff.isoformat(),
        "days_old": days_old,
        "tenants_processed": 0,
        "rows_archived": 0,
        "rows_deleted": 0,
        "files_written": 0,
        "batches": 0,
    }

    tenant_rows = fetch_all(
        """
        SELECT DISTINCT tenant_id::text AS tenant_id
        FROM security_alerts
        WHERE created_at < %s
        ORDER BY tenant_id;
        """,
        (cutoff,),
    )
    if not tenant_rows:
        return summary

    for tenant_row in tenant_rows:
        tenant_id = str(tenant_row.get("tenant_id") or "")
        if not tenant_id:
            continue
        summary["tenants_processed"] += 1
        batch_index = 0

        while True:
            rows = fetch_all(
                """
                SELECT
                    id::text,
                    tenant_id::text,
                    source_tool,
                    severity,
                    alert_title,
                    status,
                    event_time::text,
                    created_at::text,
                    destination_host,
                    hash_sha256
                FROM security_alerts
                WHERE tenant_id = %s::uuid
                  AND created_at < %s
                ORDER BY created_at
                LIMIT %s;
                """,
                (tenant_id, cutoff, batch_size),
            )
            if not rows:
                break

            ids = [str(r["id"]) for r in rows if r.get("id")]
            if not ids:
                break

            _export_batch_jsonl_gz(
                tenant_id=tenant_id,
                rows=rows,
                archive_day=archive_day,
                batch_index=batch_index,
            )
            summary["files_written"] += 1
            summary["rows_archived"] += len(rows)
            summary["batches"] += 1
            batch_index += 1

            execute(
                """
                DELETE FROM security_alerts
                WHERE id = ANY(%s::uuid[]);
                """,
                (ids,),
            )
            summary["rows_deleted"] += len(ids)

    logger.info(
        "Log archiver complete: tenants=%s archived=%s deleted=%s files=%s",
        summary["tenants_processed"],
        summary["rows_archived"],
        summary["rows_deleted"],
        summary["files_written"],
    )
    return summary


def _archiver_loop() -> None:
    days_old = int(os.getenv("LOG_ARCHIVER_DAYS_OLD", "30"))
    while True:
        try:
            archive_old_tenant_logs(days_old=days_old)
        except Exception:  # noqa: BLE001
            logger.exception("Log archiver worker iteration failed")
        time.sleep(ARCHIVER_INTERVAL_SECONDS)


def start_log_archiver_worker() -> None:
    """Start background daemon that periodically archives aged alerts."""
    global _worker_started
    if os.getenv("LOG_ARCHIVER_ENABLED", "false").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return
    with _lock:
        if _worker_started:
            return
        t = threading.Thread(target=_archiver_loop, name="log-archiver-worker", daemon=True)
        t.start()
        _worker_started = True
        logger.info("Log archiver worker started (interval=%ss)", ARCHIVER_INTERVAL_SECONDS)
