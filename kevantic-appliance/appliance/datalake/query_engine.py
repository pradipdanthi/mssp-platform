"""DuckDB query engine over local Parquet archives."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from appliance.common import metadata_db
from appliance.common.paths import datalake_root, ensure_engine_dirs

logger = logging.getLogger(__name__)


class QueryEngine:
    """Search Parquet lake by IP, domain, hash, or CVE with low RAM (DuckDB)."""

    def __init__(self, root: Optional[Path] = None) -> None:
        ensure_engine_dirs()
        self.root = root or datalake_root()

    def _glob_for_lookback(self, lookback_days: int) -> list[str]:
        if not self.root.exists():
            return []
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=lookback_days)
        paths: list[str] = []
        for day_dir in self.root.glob("*/*/*"):
            if not day_dir.is_dir():
                continue
            try:
                y, m, d = [int(x) for x in day_dir.relative_to(self.root).parts[:3]]
                day = datetime(y, m, d, tzinfo=timezone.utc).date()
            except Exception:
                continue
            if day < cutoff:
                continue
            for pq in day_dir.glob("*.parquet"):
                paths.append(pq.as_posix())
        return paths

    def search(
        self,
        iocs: Iterable[str],
        *,
        lookback_days: int = 90,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        ioc_list = [i.strip() for i in iocs if i and str(i).strip()]
        if not ioc_list:
            return []

        # Fast path: SQLite metadata index
        since = (
            datetime.now(timezone.utc) - timedelta(days=lookback_days)
        ).strftime("%Y-%m-%dT00:00:00Z")
        with metadata_db.connect() as db:
            meta_hits = metadata_db.search_metadata_iocs(
                db, ioc_list, since_ts=since, limit=limit
            )

        parquet_paths = self._glob_for_lookback(lookback_days)
        if not parquet_paths:
            return [{"source": "metadata", **h} for h in meta_hits]

        try:
            import duckdb  # type: ignore
        except ImportError:
            logger.warning("duckdb missing — returning metadata-only hits")
            return [{"source": "metadata", **h} for h in meta_hits]

        con = duckdb.connect(database=":memory:")
        # Keep RAM low: query files via glob list, projection pushdown
        file_list_sql = ", ".join(f"'{p}'" for p in parquet_paths)
        con.execute(
            f"""
            CREATE VIEW lake AS
            SELECT * FROM read_parquet([{file_list_sql}], union_by_name=True)
            """
        )
        hits: list[dict[str, Any]] = []
        for ioc in ioc_list:
            q = """
            SELECT ts, src_ip, dst_ip, domain_name, file_hash, cve, source_tool, external_id
            FROM lake
            WHERE src_ip = ? OR dst_ip = ? OR file_hash = ?
               OR domain_name = ? OR cve = ?
            LIMIT ?
            """
            cur = con.execute(q, [ioc, ioc, ioc, ioc, ioc, limit])
            cols = [d[0] for d in cur.description]
            for row in cur.fetchall():
                hits.append({"source": "parquet", **dict(zip(cols, row)), "matched_ioc": ioc})
        con.close()

        # Merge metadata hints (may point at partitions without re-scan detail)
        for h in meta_hits:
            hits.append({"source": "metadata", **h})
        return hits[:limit]
