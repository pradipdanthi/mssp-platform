"""DuckDB + ZSTD Parquet cold archive for local engine events."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from appliance.common import metadata_db
from appliance.common.paths import datalake_root, ensure_engine_dirs

logger = logging.getLogger(__name__)

RETENTION_DAYS_DEFAULT = 365
DISK_USAGE_THRESHOLD = 0.90


def _utc_today() -> datetime:
    return datetime.now(timezone.utc)


def _day_dir(root: Path, when: datetime) -> Path:
    return root / f"{when.year:04d}" / f"{when.month:02d}" / f"{when.day:02d}"


def _extract_fields(event: dict[str, Any]) -> dict[str, Optional[str]]:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    dns = data.get("dns") if isinstance(data.get("dns"), dict) else {}
    src = (
        event.get("src_ip")
        or event.get("source_ip")
        or data.get("srcip")
        or data.get("src_ip")
    )
    dst = (
        event.get("dst_ip")
        or event.get("destination_ip")
        or data.get("dstip")
        or data.get("dst_ip")
    )
    domain = (
        event.get("domain_name")
        or event.get("domain")
        or data.get("url")
        or dns.get("rrname")
        or data.get("query")
    )
    file_hash = (
        event.get("file_hash")
        or event.get("sha256")
        or event.get("md5")
        or data.get("sha256")
        or data.get("md5")
    )
    cve = event.get("cve") or data.get("cve")
    ts = str(event.get("timestamp") or event.get("event_time") or metadata_db.utc_now())
    decoder = event.get("decoder") if isinstance(event.get("decoder"), dict) else {}
    return {
        "ts": ts,
        "src_ip": str(src) if src else None,
        "dst_ip": str(dst) if dst else None,
        "domain_name": str(domain)[:255] if domain else None,
        "file_hash": str(file_hash).lower() if file_hash else None,
        "cve": str(cve).upper() if cve else None,
        "source_tool": str(
            event.get("source_tool") or decoder.get("name") or "unknown"
        ),
        "external_id": str(event.get("id") or event.get("external_alert_id") or "")
        or None,
    }


class DataLakeArchiver:
    """Ingest Wazuh/Zeek/Suricata JSON events into daily ZSTD Parquet partitions."""

    def __init__(
        self,
        root: Optional[Path] = None,
        *,
        retention_days: int = RETENTION_DAYS_DEFAULT,
        disk_threshold: float = DISK_USAGE_THRESHOLD,
    ) -> None:
        ensure_engine_dirs()
        self.root = root or datalake_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self.disk_threshold = disk_threshold

    def archive_events(
        self,
        events: Iterable[dict[str, Any]],
        *,
        when: Optional[datetime] = None,
        source_hint: str = "mixed",
    ) -> Path:
        rows = list(events)
        if not rows:
            raise ValueError("no events to archive")

        when = when or _utc_today()
        day = _day_dir(self.root, when)
        day.mkdir(parents=True, exist_ok=True)
        out = day / f"events_{source_hint}_{when.strftime('%H%M%S%f')}.parquet"

        try:
            import duckdb  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "duckdb is required for Parquet archive; pip install duckdb"
            ) from exc

        records = []
        for ev in rows:
            fields = _extract_fields(ev)
            records.append(
                {
                    **fields,
                    "raw_json": json.dumps(ev, separators=(",", ":"), default=str),
                }
            )

        con = duckdb.connect(database=":memory:")
        con.execute(
            """
            CREATE TABLE events (
              ts VARCHAR,
              src_ip VARCHAR,
              dst_ip VARCHAR,
              domain_name VARCHAR,
              file_hash VARCHAR,
              cve VARCHAR,
              source_tool VARCHAR,
              external_id VARCHAR,
              raw_json VARCHAR
            )
            """
        )
        con.executemany(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r["ts"],
                    r["src_ip"],
                    r["dst_ip"],
                    r["domain_name"],
                    r["file_hash"],
                    r["cve"],
                    r["source_tool"],
                    r["external_id"],
                    r["raw_json"],
                )
                for r in records
            ],
        )
        con.execute(
            f"COPY events TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        con.close()

        with metadata_db.connect() as db:
            for r in records:
                metadata_db.insert_metadata(
                    db,
                    ts=r["ts"] or metadata_db.utc_now(),
                    src_ip=r["src_ip"],
                    dst_ip=r["dst_ip"],
                    file_hash=r["file_hash"],
                    domain_name=r["domain_name"],
                    cve=r["cve"],
                    source_tool=r["source_tool"],
                    external_id=r["external_id"],
                    parquet_path=str(out),
                )
            db.commit()

        self.enforce_quota()
        logger.info("archived %s events -> %s", len(records), out)
        return out

    def enforce_quota(self) -> list[Path]:
        """Prune oldest daily partitions if retention or disk threshold exceeded."""
        removed: list[Path] = []
        days = sorted(
            [p for p in self.root.glob("*/*/*") if p.is_dir()],
            key=lambda p: str(p),
        )
        cutoff = _utc_today().date().toordinal() - self.retention_days
        for day_path in list(days):
            try:
                y, m, d = [int(x) for x in day_path.relative_to(self.root).parts[:3]]
                ord_ = datetime(y, m, d, tzinfo=timezone.utc).date().toordinal()
            except Exception:
                continue
            if ord_ < cutoff:
                shutil.rmtree(day_path, ignore_errors=True)
                removed.append(day_path)
                days.remove(day_path)

        usage = shutil.disk_usage(self.root)
        while days and (usage.used / max(usage.total, 1)) > self.disk_threshold:
            oldest = days.pop(0)
            shutil.rmtree(oldest, ignore_errors=True)
            removed.append(oldest)
            usage = shutil.disk_usage(self.root)
        return removed
