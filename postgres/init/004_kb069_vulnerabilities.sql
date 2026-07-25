-- KB-069: normalized vulnerability findings + recommendation link (Greenbone adapter path).
-- Additive only. No secrets. Raw finding JSON is SOC-internal never customer-facing.

BEGIN;

CREATE TABLE IF NOT EXISTS vulnerabilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    protected_asset_id UUID REFERENCES protected_assets(id) ON DELETE SET NULL,
    source_platform TEXT NOT NULL DEFAULT 'greenbone',
    external_finding_id TEXT,
    cve_id TEXT,
    nvt_oid TEXT,
    title TEXT NOT NULL,
    severity TEXT NOT NULL
        CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'fixed', 'accepted_risk', 'false_positive', 'closed')),
    customer_safe_summary TEXT,
    remediation_summary TEXT,
    internal_notes TEXT,
    raw_finding JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    recommendation_id UUID REFERENCES customer_recommendations(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vulnerabilities_tenant_severity
    ON vulnerabilities (tenant_id, severity);

CREATE INDEX IF NOT EXISTS idx_vulnerabilities_tenant_status
    ON vulnerabilities (tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_vulnerabilities_asset
    ON vulnerabilities (protected_asset_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_vulnerabilities_tenant_source_external
    ON vulnerabilities (tenant_id, source_platform, external_finding_id)
    WHERE external_finding_id IS NOT NULL;

ALTER TABLE customer_recommendations
    ADD COLUMN IF NOT EXISTS related_vulnerability_id UUID
        REFERENCES vulnerabilities(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_recommendations_related_vulnerability
    ON customer_recommendations (related_vulnerability_id);

DROP TRIGGER IF EXISTS trg_vulnerabilities_updated_at ON vulnerabilities;
CREATE TRIGGER trg_vulnerabilities_updated_at
BEFORE UPDATE ON vulnerabilities
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
