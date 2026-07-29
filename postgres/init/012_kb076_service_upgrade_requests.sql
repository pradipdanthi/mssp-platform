-- KB-076: Customer service upgrade / interest requests (e.g. Vulnerability Management).
-- Idempotent for live apply.

CREATE TABLE IF NOT EXISTS service_upgrade_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    requested_by_user_id UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    service_key TEXT NOT NULL
        CHECK (service_key IN (
            'vulnerability_management',
            'network_traffic_analysis',
            'threat_intelligence',
            'endpoint_forensics',
            'security_automation',
            'other'
        )),
    preferred_cadence TEXT NOT NULL DEFAULT 'monthly'
        CHECK (preferred_cadence IN ('weekly', 'monthly', 'quarterly', 'unsure')),
    scan_scope TEXT[] NOT NULL DEFAULT '{}',
    approximate_assets INTEGER
        CHECK (approximate_assets IS NULL OR (approximate_assets >= 1 AND approximate_assets <= 1000000)),
    environments TEXT[] NOT NULL DEFAULT '{}',
    urgency TEXT NOT NULL DEFAULT 'exploring'
        CHECK (urgency IN ('exploring', 'planning', 'needed_soon', 'urgent')),
    compliance_drivers TEXT[] NOT NULL DEFAULT '{}',
    requirements_summary TEXT NOT NULL,
    preferred_contact TEXT NOT NULL DEFAULT 'email'
        CHECK (preferred_contact IN ('email', 'phone', 'either')),
    contact_phone TEXT,
    status TEXT NOT NULL DEFAULT 'submitted'
        CHECK (status IN ('submitted', 'reviewing', 'quoted', 'accepted', 'declined', 'closed')),
    admin_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_service_upgrade_requests_tenant_created
    ON service_upgrade_requests (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_upgrade_requests_status
    ON service_upgrade_requests (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_upgrade_requests_service
    ON service_upgrade_requests (service_key, status);

DROP TRIGGER IF EXISTS trg_service_upgrade_requests_updated_at ON service_upgrade_requests;
CREATE TRIGGER trg_service_upgrade_requests_updated_at
BEFORE UPDATE ON service_upgrade_requests
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
