"""Local signed-job queue for catalogue services (IR, containment, hunt, etc.)."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from appliance.common.paths import ensure_engine_dirs, metadata_db_path, state_root


def _conn() -> sqlite3.Connection:
    ensure_engine_dirs()
    path = metadata_db_path()
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS local_jobs (
            id TEXT PRIMARY KEY,
            svc TEXT NOT NULL,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            result_json TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            claimed_by TEXT,
            cloud_job_id TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_local_jobs_svc_status ON local_jobs(svc, status, created_at)"
    )
    conn.commit()
    return conn


def enqueue(
    *,
    svc: str,
    job_type: str,
    payload: Dict[str, Any],
    cloud_job_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    jid = job_id or str(uuid.uuid4())
    now = time.time()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO local_jobs (id, svc, job_type, status, payload_json, created_at, updated_at, cloud_job_id)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (jid, svc, job_type, json.dumps(payload), now, now, cloud_job_id),
        )
        conn.commit()
    return {"job_id": jid, "svc": svc, "job_type": job_type, "status": "pending"}


def claim_next(svc: str, *, worker_id: str) -> Optional[Dict[str, Any]]:
    now = time.time()
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT id, svc, job_type, payload_json, cloud_job_id, created_at
            FROM local_jobs
            WHERE svc = ? AND status = 'pending'
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (svc,),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            """
            UPDATE local_jobs
            SET status = 'executing', claimed_by = ?, updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (worker_id, now, row["id"]),
        )
        conn.commit()
        if conn.total_changes == 0:
            return None
        return {
            "job_id": row["id"],
            "svc": row["svc"],
            "job_type": row["job_type"],
            "payload": json.loads(row["payload_json"] or "{}"),
            "cloud_job_id": row["cloud_job_id"],
            "created_at": row["created_at"],
        }


def complete(job_id: str, *, success: bool, result: Optional[Dict[str, Any]] = None) -> None:
    now = time.time()
    status = "success" if success else "failed"
    with _conn() as conn:
        conn.execute(
            """
            UPDATE local_jobs
            SET status = ?, result_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, json.dumps(result or {}), now, job_id),
        )
        conn.commit()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM local_jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return None
    return {
        "job_id": row["id"],
        "svc": row["svc"],
        "job_type": row["job_type"],
        "status": row["status"],
        "payload": json.loads(row["payload_json"] or "{}"),
        "result": json.loads(row["result_json"] or "null"),
        "cloud_job_id": row["cloud_job_id"],
        "claimed_by": row["claimed_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_jobs(svc: Optional[str] = None, *, limit: int = 50) -> List[Dict[str, Any]]:
    with _conn() as conn:
        if svc:
            rows = conn.execute(
                "SELECT * FROM local_jobs WHERE svc = ? ORDER BY created_at DESC LIMIT ?",
                (svc, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM local_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    out = []
    for row in rows:
        out.append(
            {
                "job_id": row["id"],
                "svc": row["svc"],
                "job_type": row["job_type"],
                "status": row["status"],
                "cloud_job_id": row["cloud_job_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return out


def write_status_marker() -> Path:
    path = state_root() / "engine-api.ready"
    path.write_text(f"ready_at={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n", encoding="utf-8")
    return path
