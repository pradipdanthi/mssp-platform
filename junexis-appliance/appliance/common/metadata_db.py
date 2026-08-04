"""SQLite metadata index for fast IOC lookups (complements Parquet lake)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from appliance.common.paths import ensure_engine_dirs, metadata_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS event_metadata (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  src_ip TEXT,
  dst_ip TEXT,
  file_hash TEXT,
  domain_name TEXT,
  cve TEXT,
  source_tool TEXT,
  external_id TEXT,
  parquet_path TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meta_ts ON event_metadata(ts);
CREATE INDEX IF NOT EXISTS idx_meta_src ON event_metadata(src_ip);
CREATE INDEX IF NOT EXISTS idx_meta_dst ON event_metadata(dst_ip);
CREATE INDEX IF NOT EXISTS idx_meta_hash ON event_metadata(file_hash);
CREATE INDEX IF NOT EXISTS idx_meta_domain ON event_metadata(domain_name);
CREATE INDEX IF NOT EXISTS idx_meta_cve ON event_metadata(cve);

CREATE TABLE IF NOT EXISTS telemetry_buffer (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payload_json TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL,
  last_error TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_buf_next ON telemetry_buffer(next_attempt_at);

CREATE TABLE IF NOT EXISTS hunt_jobs (
  job_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  request_json TEXT NOT NULL,
  result_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    ensure_engine_dirs()
    path = db_path or metadata_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_metadata(
    conn: sqlite3.Connection,
    *,
    ts: str,
    src_ip: Optional[str] = None,
    dst_ip: Optional[str] = None,
    file_hash: Optional[str] = None,
    domain_name: Optional[str] = None,
    cve: Optional[str] = None,
    source_tool: Optional[str] = None,
    external_id: Optional[str] = None,
    parquet_path: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO event_metadata
          (ts, src_ip, dst_ip, file_hash, domain_name, cve, source_tool,
           external_id, parquet_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts,
            src_ip,
            dst_ip,
            file_hash,
            domain_name,
            cve,
            source_tool,
            external_id,
            parquet_path,
            utc_now(),
        ),
    )


def search_metadata_iocs(
    conn: sqlite3.Connection,
    iocs: Iterable[str],
    *,
    since_ts: Optional[str] = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ioc in iocs:
        ioc = (ioc or "").strip()
        if not ioc:
            continue
        q = """
        SELECT * FROM event_metadata
        WHERE (src_ip = ? OR dst_ip = ? OR file_hash = ?
               OR domain_name = ? OR cve = ?)
        """
        params: list[Any] = [ioc, ioc, ioc, ioc, ioc]
        if since_ts:
            q += " AND ts >= ?"
            params.append(since_ts)
        q += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        for r in conn.execute(q, params):
            rows.append(dict(r))
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        rid = int(r["id"])
        if rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    return out[:limit]
