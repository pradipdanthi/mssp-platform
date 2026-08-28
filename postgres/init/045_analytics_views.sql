-- KB-111 Phase 5: Analytical scaling indexes, materialized views, and refresh helpers.

BEGIN;

-- Composite indexes for tenant-scoped time-series and facet queries (CONCURRENTLY-safe via IF NOT EXISTS).
CREATE INDEX IF NOT EXISTS idx_security_alerts_tenant_created_at
    ON security_alerts (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_alerts_tenant_source_severity
    ON security_alerts (tenant_id, source_tool, severity);

-- Pre-aggregated daily alert counts (refreshed by refresh_tenant_analytics_views()).
DROP MATERIALIZED VIEW IF EXISTS tenant_daily_alert_counts;

CREATE MATERIALIZED VIEW tenant_daily_alert_counts AS
SELECT
    tenant_id,
    (created_at AT TIME ZONE 'UTC')::date AS alert_day,
    source_tool,
    severity,
    COUNT(*)::bigint AS alert_count
FROM security_alerts
GROUP BY tenant_id, (created_at AT TIME ZONE 'UTC')::date, source_tool, severity
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_tenant_daily_alert_counts_uniq
    ON tenant_daily_alert_counts (tenant_id, alert_day, source_tool, severity);

CREATE INDEX IF NOT EXISTS idx_tenant_daily_alert_counts_tenant_day
    ON tenant_daily_alert_counts (tenant_id, alert_day DESC);

COMMENT ON MATERIALIZED VIEW tenant_daily_alert_counts IS
    'Daily alert volume by tenant/source_tool/severity; refresh via refresh_tenant_analytics_views(). '
    'Tenant isolation enforced by application queries (WHERE tenant_id) and caller RLS context.';

GRANT SELECT ON tenant_daily_alert_counts TO mssp_app;

CREATE OR REPLACE FUNCTION refresh_tenant_analytics_views()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    is_populated boolean;
BEGIN
    SELECT c.relispopulated
    INTO is_populated
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relname = 'tenant_daily_alert_counts'
      AND n.nspname = 'public'
    LIMIT 1;

    IF COALESCE(is_populated, false) THEN
        REFRESH MATERIALIZED VIEW CONCURRENTLY tenant_daily_alert_counts;
    ELSE
        REFRESH MATERIALIZED VIEW tenant_daily_alert_counts;
    END IF;
END;
$$;

COMMENT ON FUNCTION refresh_tenant_analytics_views() IS
    'Refresh analytical materialized views without blocking readers (CONCURRENTLY when possible).';

GRANT EXECUTE ON FUNCTION refresh_tenant_analytics_views() TO mssp_app;

COMMIT;
