-- KB-071: Tenant service entitlements (subscription matrix)
CREATE TABLE IF NOT EXISTS tenant_entitlements (
    tenant_id UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    wazuh_siem BOOLEAN NOT NULL DEFAULT TRUE,
    wazuh_retention_days INTEGER NOT NULL DEFAULT 30
        CHECK (wazuh_retention_days IN (30, 90, 365)),
    thehive_mode TEXT NOT NULL DEFAULT 'full'
        CHECK (thehive_mode IN ('full', 'read_only', 'off')),
    greenbone_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    greenbone_cadence TEXT NOT NULL DEFAULT 'monthly'
        CHECK (greenbone_cadence IN ('weekly', 'monthly', 'off')),
    shuffle_mode TEXT NOT NULL DEFAULT 'standard'
        CHECK (shuffle_mode IN ('standard', 'custom', 'off')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by UUID REFERENCES platform_users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_tenant_entitlements_updated
  ON tenant_entitlements(updated_at DESC);
