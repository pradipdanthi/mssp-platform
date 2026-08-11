"""Retrospective IOC hunter over local DuckDB/Parquet + metadata index."""

from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.request
from typing import Any, Optional

from appliance.common import metadata_db
from appliance.common.paths import ensure_engine_dirs, hunt_callback_url
from appliance.datalake.query_engine import QueryEngine

logger = logging.getLogger(__name__)


class RetrospectiveSweeper:
    """
    Run lookback IOC hunts against the local data lake.
    Cloud SOC submits jobs via POST /appliance/v1/jobs/retrospective-hunt.
    """

    def __init__(self) -> None:
        ensure_engine_dirs()
        self.engine = QueryEngine()

    def run_job(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job.get("job_id") or "").strip()
        iocs = job.get("iocs") or []
        lookback_days = int(job.get("lookback_days") or 90)
        if not job_id:
            raise ValueError("job_id is required")
        if not isinstance(iocs, list) or not iocs:
            raise ValueError("iocs must be a non-empty list")

        now = metadata_db.utc_now()
        with metadata_db.connect() as db:
            db.execute(
                """
                INSERT INTO hunt_jobs (job_id, status, request_json, result_json, created_at, updated_at)
                VALUES (?, 'running', ?, NULL, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                  status='running', request_json=excluded.request_json, updated_at=excluded.updated_at
                """,
                (job_id, json.dumps(job), now, now),
            )
            db.commit()

        try:
            hits = self.engine.search(iocs, lookback_days=lookback_days, limit=500)
            # Never return raw_json / passwords to cloud — metadata fields only
            safe_hits = []
            for h in hits:
                safe_hits.append(
                    {
                        k: h.get(k)
                        for k in (
                            "source",
                            "ts",
                            "src_ip",
                            "dst_ip",
                            "domain_name",
                            "file_hash",
                            "cve",
                            "source_tool",
                            "external_id",
                            "matched_ioc",
                            "parquet_path",
                        )
                        if k in h and h.get(k) is not None
                    }
                )
            result = {
                "job_id": job_id,
                "status": "completed",
                "lookback_days": lookback_days,
                "ioc_count": len(iocs),
                "hit_count": len(safe_hits),
                "hits": safe_hits,
                "completed_at": metadata_db.utc_now(),
            }
            with metadata_db.connect() as db:
                db.execute(
                    """
                    UPDATE hunt_jobs
                    SET status='completed', result_json=?, updated_at=?
                    WHERE job_id=?
                    """,
                    (json.dumps(result), metadata_db.utc_now(), job_id),
                )
                db.commit()
            self._callback(result)
            return result
        except Exception as exc:  # noqa: BLE001
            err = {
                "job_id": job_id,
                "status": "failed",
                "error": str(exc),
                "completed_at": metadata_db.utc_now(),
            }
            with metadata_db.connect() as db:
                db.execute(
                    """
                    UPDATE hunt_jobs
                    SET status='failed', result_json=?, updated_at=?
                    WHERE job_id=?
                    """,
                    (json.dumps(err), metadata_db.utc_now(), job_id),
                )
                db.commit()
            logger.exception("retrospective hunt failed job_id=%s", job_id)
            raise

    def _callback(self, result: dict[str, Any]) -> None:
        url = hunt_callback_url()
        appliance_id = os.environ.get("KEVANTIC_APPLIANCE_ID", "")
        api_key = os.environ.get("KEVANTIC_APPLIANCE_API_KEY", "")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if appliance_id and api_key:
            headers["X-Appliance-ID"] = appliance_id
            headers["X-Appliance-API-Key"] = api_key
        try:
            data = json.dumps(result).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                logger.info("hunt callback status=%s", resp.status)
        except Exception as exc:  # noqa: BLE001
            # Local result remains in SQLite; cloud can pull later
            logger.warning("hunt callback failed: %s", exc)

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        with metadata_db.connect() as db:
            row = db.execute(
                "SELECT job_id, status, request_json, result_json, created_at, updated_at "
                "FROM hunt_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        if out.get("result_json"):
            out["result"] = json.loads(out["result_json"])
        if out.get("request_json"):
            out["request"] = json.loads(out["request_json"])
        return out
