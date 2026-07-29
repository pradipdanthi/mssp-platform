-- KB-086: Asset-scoped service coverage (e.g. Vulnerability Management on selected hosts only).

ALTER TABLE service_upgrade_requests
  ADD COLUMN IF NOT EXISTS requested_asset_ids UUID[] NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS tenant_asset_service_coverage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES protected_assets(id) ON DELETE CASCADE,
    service_key TEXT NOT NULL
        CHECK (service_key IN (
            'vulnerability_management',
            'network_traffic_analysis',
            'threat_intelligence',
            'endpoint_forensics',
            'security_automation',
            'other'
        )),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive')),
    enabled_by UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, asset_id, service_key)
);

CREATE INDEX IF NOT EXISTS idx_asset_service_coverage_tenant_service
    ON tenant_asset_service_coverage (tenant_id, service_key, status);

CREATE INDEX IF NOT EXISTS idx_asset_service_coverage_asset
    ON tenant_asset_service_coverage (asset_id);

DROP TRIGGER IF EXISTS trg_tenant_asset_service_coverage_updated_at ON tenant_asset_service_coverage;
CREATE TRIGGER trg_tenant_asset_service_coverage_updated_at
BEFORE UPDATE ON tenant_asset_service_coverage
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
