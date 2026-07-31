-- Threat Intelligence & Enrichment — IOCs + campaign bulletins.
-- Idempotent for live apply.

CREATE TABLE IF NOT EXISTS tenant_threat_intel_iocs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    ioc_value TEXT NOT NULL,
    ioc_type TEXT NOT NULL
        CHECK (ioc_type IN ('IP', 'DOMAIN', 'FILE_HASH', 'URL')),
    threat_actor TEXT NOT NULL DEFAULT 'Unknown',
    confidence_score INTEGER NOT NULL DEFAULT 50
        CHECK (confidence_score >= 0 AND confidence_score <= 100),
    reputation_status TEXT NOT NULL
        CHECK (reputation_status IN ('MALICIOUS', 'SUSPICIOUS', 'BENIGN')),
    mitre_tactics JSONB NOT NULL DEFAULT '[]'::jsonb,
    mitre_techniques JSONB NOT NULL DEFAULT '[]'::jsonb,
    summary TEXT NOT NULL DEFAULT '',
    recommended_action TEXT NOT NULL DEFAULT '',
    related_alert_count INTEGER NOT NULL DEFAULT 0 CHECK (related_alert_count >= 0),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'expired', 'dismissed')),
    raw_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_seen_in_tenant TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, ioc_type, ioc_value)
);

CREATE INDEX IF NOT EXISTS idx_tenant_ti_iocs_tenant_rep
    ON tenant_threat_intel_iocs (tenant_id, reputation_status, confidence_score DESC);
CREATE INDEX IF NOT EXISTS idx_tenant_ti_iocs_type
    ON tenant_threat_intel_iocs (tenant_id, ioc_type, last_seen_in_tenant DESC);

CREATE TABLE IF NOT EXISTS tenant_threat_intel_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    campaign_name TEXT NOT NULL,
    target_industry TEXT NOT NULL DEFAULT 'General',
    severity TEXT NOT NULL
        CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM')),
    summary TEXT NOT NULL DEFAULT '',
    recommended_defenses TEXT NOT NULL DEFAULT '',
    threat_actor TEXT,
    mitre_techniques JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, campaign_name)
);

CREATE INDEX IF NOT EXISTS idx_tenant_ti_campaigns_tenant
    ON tenant_threat_intel_campaigns (tenant_id, severity, published_at DESC);

DROP TRIGGER IF EXISTS trg_tenant_threat_intel_iocs_updated_at ON tenant_threat_intel_iocs;
CREATE TRIGGER trg_tenant_threat_intel_iocs_updated_at
BEFORE UPDATE ON tenant_threat_intel_iocs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tenant_threat_intel_campaigns_updated_at ON tenant_threat_intel_campaigns;
CREATE TRIGGER trg_tenant_threat_intel_campaigns_updated_at
BEFORE UPDATE ON tenant_threat_intel_campaigns
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
