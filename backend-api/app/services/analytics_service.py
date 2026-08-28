"""
Phase 5: Analytical query adapter — PostgreSQL materialized views + optional ClickHouse OLAP.

Routes large threat-hunting queries to ClickHouse when CLICKHOUSE_HOST is set;
falls back to optimized PostgreSQL views when unconfigured or unreachable.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

from app.db.session import fetch_all, fetch_one

logger = logging.getLogger(__name__)

THREAT_HUNT_SOURCE_TOOLS = frozenset({"suricata", "zeek", "wazuh"})
CLICKHOUSE_TIMEOUT_SECONDS = 5.0


def _parse_date(value: date | datetime | str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        raise ValueError("date value required")
    return date.fromisoformat(text[:10])


class ClickHouseAnalyticsAdapter:
    """Thin HTTP client for ClickHouse OLAP queries (no extra dependency)."""

    def __init__(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ) -> None:
        self.host = (host if host is not None else os.getenv("CLICKHOUSE_HOST") or "").strip()
        self.port = int(port if port is not None else (os.getenv("CLICKHOUSE_PORT") or "8123"))
        self.user = (user if user is not None else os.getenv("CLICKHOUSE_USER") or "default").strip()
        self.password = (
            password if password is not None else os.getenv("CLICKHOUSE_PASSWORD") or ""
        ).strip()
        self.database = (
            database if database is not None else os.getenv("CLICKHOUSE_DATABASE") or "default"
        ).strip()

    def is_configured(self) -> bool:
        return bool(self.host)

    def is_healthy(self) -> bool:
        if not self.is_configured():
            return False
        try:
            self._execute("SELECT 1", format_json=False)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _base_url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def _execute(self, sql: str, *, format_json: bool = True) -> str:
        params: Dict[str, str] = {}
        if format_json:
            params["default_format"] = "JSONEachRow"
        if self.database:
            params["database"] = self.database
        query_string = urllib.parse.urlencode(params)
        url = f"{self._base_url()}?{query_string}" if query_string else self._base_url()
        headers = {"Content-Type": "text/plain; charset=utf-8"}
        if self.user:
            token = f"{self.user}:{self.password}".encode("utf-8")
            import base64

            headers["Authorization"] = "Basic " + base64.b64encode(token).decode("ascii")
        req = urllib.request.Request(
            url,
            data=sql.encode("utf-8"),
            method="POST",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=CLICKHOUSE_TIMEOUT_SECONDS) as resp:
            return resp.read().decode("utf-8")

    def query_tenant_alert_metrics(
        self,
        tenant_id: str,
        start_date: date,
        end_date: date,
        *,
        source_tools: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query pre-aggregated daily counts from ClickHouse security_alerts_daily table.
        Table/column names mirror PostgreSQL matview for portability.
        """
        tools = [t for t in (source_tools or THREAT_HUNT_SOURCE_TOOLS) if t]
        if not tools:
            tools = sorted(THREAT_HUNT_SOURCE_TOOLS)
        in_list = ", ".join(f"'{t.replace(chr(39), '')}'" for t in tools)
        sql = f"""
SELECT
    alert_day,
    source_tool,
    severity,
    sum(alert_count) AS alert_count
FROM security_alerts_daily
WHERE tenant_id = '{tenant_id.replace(chr(39), '')}'
  AND alert_day >= '{start_date.isoformat()}'
  AND alert_day <= '{end_date.isoformat()}'
  AND source_tool IN ({in_list})
GROUP BY alert_day, source_tool, severity
ORDER BY alert_day DESC, source_tool, severity
"""
        raw = self._execute(sql)
        rows: List[Dict[str, Any]] = []
        for line in raw.strip().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            rows.append(
                {
                    "alert_day": str(row.get("alert_day") or ""),
                    "source_tool": row.get("source_tool"),
                    "severity": row.get("severity"),
                    "alert_count": int(row.get("alert_count") or 0),
                    "engine": "clickhouse",
                }
            )
        return rows


def _postgres_tenant_alert_metrics(
    tenant_id: str,
    start_date: date,
    end_date: date,
    *,
    source_tools: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    params: List[Any] = [tenant_id, start_date, end_date]
    tool_filter = ""
    if source_tools:
        tools = [t for t in source_tools if t]
        if tools:
            tool_filter = " AND source_tool = ANY(%s)"
            params.append(list(tools))
    rows = fetch_all(
        f"""
        SELECT
            alert_day::text AS alert_day,
            source_tool,
            severity,
            alert_count
        FROM tenant_daily_alert_counts
        WHERE tenant_id = %s::uuid
          AND alert_day >= %s::date
          AND alert_day <= %s::date
          {tool_filter}
        ORDER BY alert_day DESC, source_tool, severity;
        """,
        tuple(params),
    )
    return [
        {
            "alert_day": row.get("alert_day"),
            "source_tool": row.get("source_tool"),
            "severity": row.get("severity"),
            "alert_count": int(row.get("alert_count") or 0),
            "engine": "postgresql",
        }
        for row in (rows or [])
    ]


def get_tenant_alert_metrics(
    tenant_id: str,
    start_date: date | datetime | str,
    end_date: date | datetime | str,
    *,
    source_tools: Optional[Sequence[str]] = None,
    clickhouse: Optional[ClickHouseAnalyticsAdapter] = None,
) -> Dict[str, Any]:
    """
    Return pre-aggregated daily alert metrics for a tenant.

  RLS: caller must bind ``set_db_session_context`` for customer-scoped users;
  SOC roles may query any tenant when app.current_role is set.
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    tools = list(source_tools) if source_tools else None
    hunt_tools = set(tools or THREAT_HUNT_SOURCE_TOOLS)
    use_clickhouse_path = bool(hunt_tools & THREAT_HUNT_SOURCE_TOOLS)

    adapter = clickhouse if clickhouse is not None else ClickHouseAnalyticsAdapter()
    engine = "postgresql"
    rows: List[Dict[str, Any]] = []

    if use_clickhouse_path and adapter.is_configured():
        if adapter.is_healthy():
            try:
                rows = adapter.query_tenant_alert_metrics(
                    tenant_id,
                    start,
                    end,
                    source_tools=tools or sorted(THREAT_HUNT_SOURCE_TOOLS),
                )
                engine = "clickhouse"
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ClickHouse unreachable for tenant %s; falling back to PostgreSQL. (%s)",
                    tenant_id,
                    exc,
                )
        else:
            logger.warning(
                "ClickHouse host configured but unhealthy; falling back to PostgreSQL."
            )

    if not rows:
        rows = _postgres_tenant_alert_metrics(
            tenant_id,
            start,
            end,
            source_tools=tools,
        )
        engine = "postgresql"

    return {
        "tenant_id": tenant_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "engine": engine,
        "rows": rows,
        "total_alerts": sum(int(r.get("alert_count") or 0) for r in rows),
    }


def refresh_tenant_analytics_views() -> None:
    """Refresh materialized analytical views (CONCURRENTLY when possible)."""
    fetch_one("SELECT refresh_tenant_analytics_views();")
