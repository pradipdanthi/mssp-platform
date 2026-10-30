-- KB TIA Increment 4: evidence dossier, reviewed runbooks, per-tenant research
-- authorisation, and a ledger of logical side effects (ticket notes, closures).
-- Additive only. Not applied to the live database by this change.

-- What reached the investigator, per attempt: section, source, freshness, gaps, hash.
ALTER TABLE tia_investigation_attempts ADD COLUMN IF NOT EXISTS evidence_manifest JSONB;

-- ---------------------------------------------------------------------
-- Runbooks: only approved rows are retrieved as investigation context.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tia_runbooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    detection_key TEXT NOT NULL CHECK (btrim(detection_key) <> ''),
    title TEXT NOT NULL CHECK (btrim(title) <> ''),
    body TEXT NOT NULL CHECK (btrim(body) <> ''),
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'retired')),
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    source_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (detection_key, version),
    CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND btrim(approved_by) <> '' AND approved_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_tia_runbooks_key ON tia_runbooks (detection_key, version DESC) WHERE status = 'approved';

-- ---------------------------------------------------------------------
-- Research: a tenant must authorise each provider and query class. A global
-- domain allow-list is necessary but never sufficient.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tia_research_grants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (btrim(provider) <> ''),
    query_class TEXT NOT NULL
        CHECK (query_class IN ('public_identifier', 'ip_reputation', 'hash_reputation', 'behavioural_query', 'investigation_context')),
    approved_by TEXT NOT NULL CHECK (btrim(approved_by) <> ''),
    customer_reference TEXT NOT NULL CHECK (btrim(customer_reference) <> ''),
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to > valid_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tia_research_grants_live
    ON tia_research_grants (tenant_id, provider, query_class) WHERE revoked_at IS NULL;

-- Every outbound query, including refusals, so a disclosure can always be audited.
CREATE TABLE IF NOT EXISTS tia_research_disclosures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    alert_id UUID REFERENCES security_alerts(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    query_class TEXT NOT NULL,
    query_text TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('sent', 'refused', 'failed')),
    refusal_reason TEXT,
    http_status INTEGER,
    source_url TEXT,
    fetched_at TIMESTAMPTZ,
    excerpt TEXT,
    requested_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tia_research_disclosures_alert ON tia_research_disclosures (alert_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tia_research_disclosures_tenant ON tia_research_disclosures (tenant_id, created_at DESC);

-- ---------------------------------------------------------------------
-- Logical effects. One row per intended effect, keyed by what the effect IS
-- (kind + alert + evidence version), not by which attempt produced it. Attempts
-- are appended to the history; a retry with a new attempt id finds the row.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tia_effects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    logical_key TEXT NOT NULL UNIQUE,
    effect_kind TEXT NOT NULL CHECK (effect_kind IN ('ticket_note', 'external_ticket_note', 'closure')),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    alert_id UUID NOT NULL REFERENCES security_alerts(id) ON DELETE CASCADE,
    incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
    evidence_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'committed', 'uncertain', 'skipped')),
    skip_reason TEXT,
    target_ref TEXT,
    first_attempt_id UUID,
    attempt_history JSONB NOT NULL DEFAULT '[]'::jsonb,
    content_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    committed_at TIMESTAMPTZ,
    uncertain_since TIMESTAMPTZ,
    verified_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_tia_effects_alert ON tia_effects (alert_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tia_effects_uncertain ON tia_effects (uncertain_since) WHERE status = 'uncertain';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mssp_app') THEN
        GRANT SELECT ON tia_runbooks TO mssp_app;
        GRANT SELECT, INSERT, UPDATE ON tia_research_grants, tia_effects TO mssp_app;
        GRANT SELECT, INSERT, UPDATE ON tia_research_disclosures TO mssp_app;
    END IF;
END
$$;

COMMENT ON TABLE tia_research_grants IS
    'Empty by default: no customer data leaves the platform for research until the customer authorises a provider and query class.';

INSERT INTO tia_schema_version (component, version) VALUES ('tia_evidence', 122)
ON CONFLICT (component) DO UPDATE SET version = GREATEST(tia_schema_version.version, EXCLUDED.version);
