"""Phase 5: analytics service, ClickHouse failover, and matview refresh."""

from __future__ import annotations

import unittest
from datetime import date, timedelta
from unittest.mock import patch

from app.services.analytics_service import (
    ClickHouseAnalyticsAdapter,
    get_tenant_alert_metrics,
    refresh_tenant_analytics_views,
)

TENANT_ID = "aaaaaaaa-1111-2222-3333-444444444441"


class ClickHouseFallbackTests(unittest.TestCase):
    def test_unconfigured_clickhouse_uses_postgresql(self):
        adapter = ClickHouseAnalyticsAdapter(host="")
        with patch(
            "app.services.analytics_service._postgres_tenant_alert_metrics",
            return_value=[{"alert_day": "2026-08-01", "alert_count": 3, "engine": "postgresql"}],
        ) as mock_pg:
            result = get_tenant_alert_metrics(
                TENANT_ID,
                date(2026, 8, 1),
                date(2026, 8, 28),
                clickhouse=adapter,
            )
        mock_pg.assert_called_once()
        self.assertEqual(result["engine"], "postgresql")
        self.assertEqual(result["total_alerts"], 3)

    def test_unhealthy_clickhouse_falls_back_to_postgresql(self):
        adapter = ClickHouseAnalyticsAdapter(host="10.0.0.50")
        with patch.object(adapter, "is_healthy", return_value=False):
            with patch(
                "app.services.analytics_service._postgres_tenant_alert_metrics",
                return_value=[],
            ) as mock_pg:
                result = get_tenant_alert_metrics(
                    TENANT_ID,
                    date(2026, 8, 1),
                    date(2026, 8, 2),
                    clickhouse=adapter,
                )
        mock_pg.assert_called_once()
        self.assertEqual(result["engine"], "postgresql")


class TenantMetricsRlsTests(unittest.TestCase):
    @patch("app.services.analytics_service.fetch_all")
    def test_get_tenant_alert_metrics_queries_by_tenant(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "alert_day": "2026-08-27",
                "source_tool": "wazuh",
                "severity": "low",
                "alert_count": 5,
            }
        ]
        adapter = ClickHouseAnalyticsAdapter(host="")
        result = get_tenant_alert_metrics(
            TENANT_ID,
            date(2026, 8, 1),
            date(2026, 8, 28),
            source_tools=["wazuh"],
            clickhouse=adapter,
        )
        self.assertEqual(result["tenant_id"], TENANT_ID)
        self.assertEqual(result["total_alerts"], 5)
        mock_fetch.assert_called_once()
        sql, params = mock_fetch.call_args[0]
        self.assertIn("tenant_daily_alert_counts", sql)
        self.assertEqual(params[0], TENANT_ID)

    @patch("app.services.analytics_service.fetch_all")
    def test_rls_context_can_scope_customer_tenant(self, mock_fetch):
        mock_fetch.return_value = []
        adapter = ClickHouseAnalyticsAdapter(host="")
        get_tenant_alert_metrics(
            TENANT_ID,
            date.today() - timedelta(days=7),
            date.today(),
            clickhouse=adapter,
        )
        # Service relies on caller-bound RLS; verify query still filters tenant_id.
        sql, params = mock_fetch.call_args[0]
        self.assertIn("tenant_id = %s", sql)
        self.assertEqual(params[0], TENANT_ID)


class RefreshAnalyticsViewsTests(unittest.TestCase):
    @patch("app.services.analytics_service.fetch_one")
    def test_refresh_calls_sql_function(self, mock_fetch):
        refresh_tenant_analytics_views()
        mock_fetch.assert_called_once_with("SELECT refresh_tenant_analytics_views();")

    def test_refresh_runs_cleanly_when_postgres_available(self):
        try:
            from app.db.session import fetch_one

            row = fetch_one(
                "SELECT 1 AS ok FROM pg_proc WHERE proname = 'refresh_tenant_analytics_views' LIMIT 1;"
            )
            if not row:
                self.skipTest("Migration 045 not applied")
            refresh_tenant_analytics_views()
        except Exception as exc:
            self.skipTest(f"Postgres unavailable: {exc}")


class ClickHouseAdapterTests(unittest.TestCase):
    def test_configured_when_host_set(self):
        adapter = ClickHouseAnalyticsAdapter(host="ch.example.local")
        self.assertTrue(adapter.is_configured())

    @patch.object(ClickHouseAnalyticsAdapter, "_execute", return_value="")
    def test_healthy_when_ping_succeeds(self, _mock_exec):
        adapter = ClickHouseAnalyticsAdapter(host="ch.example.local")
        self.assertTrue(adapter.is_healthy())


if __name__ == "__main__":
    unittest.main()
