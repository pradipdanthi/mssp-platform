-- KB-072: Tenant engine provisioning mappings (Wazuh group + TheHive org/tag).
-- Additive only. Control plane remains system of record for tenants.

CREATE TABLE IF NOT EXISTS tenant_engine_bindings (
    tenant_id UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    wazuh_agent_group TEXT NOT NULL,
    wazuh_group_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (wazuh_group_status IN ('pending', 'provisioned', 'error', 'skipped')),
    wazuh_last_error TEXT,
    wazuh_provisioned_at TIMESTAMPTZ,
    thehive_org_name TEXT NOT NULL,
    thehive_tenant_tag TEXT NOT NULL,
    thehive_org_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (thehive_org_status IN ('pending', 'provisioned', 'error', 'skipped', 'tag_only')),
    thehive_last_error TEXT,
    thehive_provisioned_at TIMESTAMPTZ,
    last_provision_attempt_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tenant_engine_bindings_wazuh_group
    ON tenant_engine_bindings (wazuh_agent_group);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tenant_engine_bindings_thehive_tag
    ON tenant_engine_bindings (thehive_tenant_tag);

CREATE INDEX IF NOT EXISTS idx_tenant_engine_bindings_thehive_org
    ON tenant_engine_bindings (thehive_org_name);
