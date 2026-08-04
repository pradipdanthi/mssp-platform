"""Junexis Data Lake — DuckDB queries over cloud/SOC Parquet partitions (Modes 1/3)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def cloud_datalake_root() -> Path:
    return Path(os.getenv("JUNEXIS_CLOUD_DATALAKE_ROOT", "/var/lib/junexis/datalake"))


def tenant_lake_path(tenant_id: str) -> Path:
    return cloud_datalake_root() / str(tenant_id)


def _glob_parquet(root: Path, lookback_days: int) -> List[str]:
    if not root.exists():
        return []
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=lookback_days)
    paths: List[str] = []
    for day_dir in root.glob("*/*/*"):
        if not day_dir.is_dir():
            continue
        try:
            y, m, d = [int(x) for x in day_dir.relative_to(root).parts[:3]]
            day = datetime(y, m, d, tzinfo=timezone.utc).date()
        except Exception:
            continue
        if day < cutoff:
            continue
        for pq in day_dir.glob("*.parquet"):
            paths.append(pq.as_posix())
    # Also accept flat dumps
    for pq in root.glob("**/*.parquet"):
        p = pq.as_posix()
        if p not in paths:
            paths.append(p)
    return paths[:500]


def search_iocs(
    tenant_id: str,
    iocs: Iterable[str],
    *,
    lookback_days: int = 90,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Search Junexis Data Lake Parquet for IOC hits. Empty lake → empty list (not an error)."""
    ioc_list = [str(i).strip() for i in iocs if i and str(i).strip()]
    if not ioc_list:
        return []

    root = tenant_lake_path(tenant_id)
    parquet_paths = _glob_parquet(root, lookback_days)
    if not parquet_paths:
        logger.info(
            "cloud datalake empty tenant=%s root=%s — returning zero hits",
            tenant_id,
            root,
        )
        return []

    try:
        import duckdb  # type: ignore
    except ImportError:
        logger.warning("duckdb not installed — cloud retrospective unavailable")
        return []

    con = duckdb.connect(database=":memory:")
    file_list_sql = ", ".join("'" + p.replace("'", "''") + "'" for p in parquet_paths)
    try:
        con.execute(
            f"""
            CREATE VIEW lake AS
            SELECT * FROM read_parquet([{file_list_sql}], union_by_name=True)
            """
        )
    except Exception as exc:
        logger.warning("duckdb parquet open failed: %s", exc)
        return []

    # Flexible column names across engines
    cols = {r[0].lower() for r in con.execute("DESCRIBE lake").fetchall()}
    candidates = []
    for name in (
        "src_ip",
        "dst_ip",
        "ip",
        "source_ip",
        "destination_ip",
        "domain",
        "domain_name",
        "host",
        "hostname",
        "file_hash",
        "sha256",
        "md5",
        "hash",
        "cve",
        "indicator",
        "ioc",
    ):
        if name in cols:
            candidates.append(name)
    if not candidates:
        return []

    ors = " OR ".join(f"CAST({c} AS VARCHAR) = ?" for c in candidates)
    hits: List[Dict[str, Any]] = []
    col_names = [r[0] for r in con.execute("DESCRIBE lake").fetchall()]
    for ioc in ioc_list:
        params = [ioc] * len(candidates)
        try:
            rows = con.execute(
                f"SELECT * FROM lake WHERE {ors} LIMIT {int(limit)}",
                params,
            ).fetchall()
        except Exception:
            continue
        for row in rows:
            record = {
                col_names[i]: (None if _is_na(row[i]) else row[i])
                for i in range(min(len(col_names), len(row)))
            }
            hits.append(
                {
                    "source": "junexis_data_lake",
                    "matched_ioc": ioc,
                    "record": record,
                }
            )
            if len(hits) >= limit:
                return hits
    return hits


def _is_na(v: Any) -> bool:
    try:
        import math

        if v is None:
            return True
        if isinstance(v, float) and math.isnan(v):
            return True
    except Exception:
        pass
    return False
