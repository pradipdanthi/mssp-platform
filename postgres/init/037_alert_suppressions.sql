-- Alert suppressions: mute matching future alerts before incident creation.
-- Scope: global (tenant_id NULL) | tenant | host (hostname required).

CREATE TABLE IF NOT EXISTS alert_suppressions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    hostname TEXT,
    rule_id TEXT NOT NULL,
    scope TEXT NOT NULL
        CHECK (scope IN ('global', 'tenant', 'host')),
    match_process_path BOOLEAN NOT NULL DEFAULT false,
    process_path_value TEXT,
    match_parent_process BOOLEAN NOT NULL DEFAULT false,
    parent_process_value TEXT,
    match_file_hash BOOLEAN NOT NULL DEFAULT false,
    file_hash_value TEXT,
    match_hostname BOOLEAN NOT NULL DEFAULT false,
    hostname_value TEXT,
    expires_at TIMESTAMPTZ,
    reason TEXT,
    created_by_user_id UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    disabled_at TIMESTAMPTZ,
    CONSTRAINT alert_suppressions_scope_tenant_chk CHECK (
        (scope = 'global' AND tenant_id IS NULL AND hostname IS NULL)
        OR (scope = 'tenant' AND tenant_id IS NOT NULL AND hostname IS NULL)
        OR (scope = 'host' AND tenant_id IS NOT NULL AND hostname IS NOT NULL)
    ),
    CONSTRAINT alert_suppressions_match_values_chk CHECK (
        (NOT match_process_path OR (process_path_value IS NOT NULL AND btrim(process_path_value) <> ''))
        AND (NOT match_parent_process OR (parent_process_value IS NOT NULL AND btrim(parent_process_value) <> ''))
        AND (NOT match_file_hash OR (file_hash_value IS NOT NULL AND btrim(file_hash_value) <> ''))
        AND (NOT match_hostname OR (hostname_value IS NOT NULL AND btrim(hostname_value) <> ''))
    )
);

CREATE INDEX IF NOT EXISTS idx_alert_suppressions_rule_id
    ON alert_suppressions (rule_id);

CREATE INDEX IF NOT EXISTS idx_alert_suppressions_tenant_rule
    ON alert_suppressions (tenant_id, rule_id);

CREATE INDEX IF NOT EXISTS idx_alert_suppressions_expires_at
    ON alert_suppressions (expires_at)
    WHERE disabled_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_alert_suppressions_active_lookup
    ON alert_suppressions (rule_id, scope, tenant_id)
    WHERE disabled_at IS NULL;

COMMENT ON TABLE alert_suppressions IS
  'SOC suppressions: matching ingest alerts become false_positive, customer_visible=false, no incident.';
COMMENT ON COLUMN alert_suppressions.tenant_id IS
  'NULL for global suppressions; required for tenant/host scope.';
COMMENT ON COLUMN alert_suppressions.hostname IS
  'Required when scope=host; single-host mute within tenant.';
COMMENT ON COLUMN alert_suppressions.disabled_at IS
  'Soft-disable timestamp; NULL means active (subject to expires_at).';
