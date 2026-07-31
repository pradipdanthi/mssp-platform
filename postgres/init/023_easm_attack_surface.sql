-- External Attack Surface Management (EASM) — perimeter assets, scans, findings.
-- Idempotent for live apply.

ALTER TABLE tenant_entitlements
    ADD COLUMN IF NOT EXISTS external_attack_surface_enabled BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS tenant_easm_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    domain_or_ip TEXT NOT NULL,
    asset_type TEXT NOT NULL
        CHECK (asset_type IN ('PRIMARY_DOMAIN', 'SUBDOMAIN', 'PUBLIC_IP')),
    discovery_source TEXT NOT NULL DEFAULT 'customer_registration',
    parent_asset_id UUID REFERENCES tenant_easm_assets(id) ON DELETE SET NULL,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, domain_or_ip)
);

CREATE INDEX IF NOT EXISTS idx_tenant_easm_assets_tenant_status
    ON tenant_easm_assets (tenant_id, status, asset_type);

CREATE TABLE IF NOT EXISTS tenant_easm_scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    target_domain TEXT NOT NULL,
    scan_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (scan_status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),
    open_ports_count INTEGER NOT NULL DEFAULT 0 CHECK (open_ports_count >= 0),
    vulnerabilities_count INTEGER NOT NULL DEFAULT 0 CHECK (vulnerabilities_count >= 0),
    ssl_status TEXT
        CHECK (ssl_status IS NULL OR ssl_status IN ('VALID', 'EXPIRING_SOON', 'EXPIRED', 'UNKNOWN', 'NONE')),
    assets_discovered INTEGER NOT NULL DEFAULT 0 CHECK (assets_discovered >= 0),
    findings_count INTEGER NOT NULL DEFAULT 0 CHECK (findings_count >= 0),
    error_message TEXT,
    executed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_easm_scans_tenant
    ON tenant_easm_scans (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS tenant_easm_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES tenant_easm_scans(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    asset_name TEXT NOT NULL,
    finding_type TEXT NOT NULL
        CHECK (finding_type IN (
            'OPEN_PORT',
            'EXPIRED_SSL',
            'EXPIRING_SSL',
            'WEB_VULNERABILITY',
            'SUBDOMAIN_TAKEOVER',
            'EXPOSED_SERVICE',
            'INFO'
        )),
    severity TEXT NOT NULL
        CHECK (severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    remediation TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'resolved', 'accepted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_easm_findings_tenant_sev
    ON tenant_easm_findings (tenant_id, severity, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenant_easm_findings_scan
    ON tenant_easm_findings (scan_id, severity);

DROP TRIGGER IF EXISTS trg_tenant_easm_assets_updated_at ON tenant_easm_assets;
CREATE TRIGGER trg_tenant_easm_assets_updated_at
BEFORE UPDATE ON tenant_easm_assets
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tenant_easm_scans_updated_at ON tenant_easm_scans;
CREATE TRIGGER trg_tenant_easm_scans_updated_at
BEFORE UPDATE ON tenant_easm_scans
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tenant_easm_findings_updated_at ON tenant_easm_findings;
CREATE TRIGGER trg_tenant_easm_findings_updated_at
BEFORE UPDATE ON tenant_easm_findings
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
