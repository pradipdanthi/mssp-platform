-- KB-111 Phase 2: Defense-in-depth Row Level Security for core tenant tables.

BEGIN;

-- Session GUCs (set per transaction from backend-api):
--   app.current_tenant  — customer tenant UUID string (empty = unset)
--   app.current_role    — platform role (SOC roles bypass tenant filter)
--
-- Application connections pool as mssp_admin but SET ROLE mssp_app per
-- transaction so RLS is enforced (superusers always bypass RLS).

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mssp_app') THEN
        CREATE ROLE mssp_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO mssp_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mssp_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mssp_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mssp_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO mssp_app;
GRANT mssp_app TO mssp_admin;

CREATE OR REPLACE FUNCTION app_rls_tenant_visible(row_tenant_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT
        COALESCE(NULLIF(current_setting('app.current_role', true), ''), '')
            IN ('platform_admin', 'soc_manager', 'soc_analyst')
        OR NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR row_tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid;
$$;

COMMENT ON FUNCTION app_rls_tenant_visible(uuid) IS
    'RLS helper: SOC roles and unset app.current_tenant bypass; else match tenant_id.';

-- security_alerts
ALTER TABLE security_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_alerts FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS security_alerts_tenant_isolation ON security_alerts;
CREATE POLICY security_alerts_tenant_isolation ON security_alerts
    FOR ALL
    USING (app_rls_tenant_visible(tenant_id))
    WITH CHECK (app_rls_tenant_visible(tenant_id));

-- incidents
ALTER TABLE incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS incidents_tenant_isolation ON incidents;
CREATE POLICY incidents_tenant_isolation ON incidents
    FOR ALL
    USING (app_rls_tenant_visible(tenant_id))
    WITH CHECK (app_rls_tenant_visible(tenant_id));

-- vulnerabilities
ALTER TABLE vulnerabilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE vulnerabilities FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS vulnerabilities_tenant_isolation ON vulnerabilities;
CREATE POLICY vulnerabilities_tenant_isolation ON vulnerabilities
    FOR ALL
    USING (app_rls_tenant_visible(tenant_id))
    WITH CHECK (app_rls_tenant_visible(tenant_id));

GRANT EXECUTE ON FUNCTION app_rls_tenant_visible(uuid) TO mssp_app;
GRANT EXECUTE ON FUNCTION purge_expired_tenant_data(integer) TO mssp_app;

COMMIT;
