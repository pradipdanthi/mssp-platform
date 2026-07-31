-- Continuous Compliance & Hardening (CaaS) — Wazuh SCA normalized store.
-- Idempotent for live apply.

ALTER TABLE tenant_entitlements
    ADD COLUMN IF NOT EXISTS continuous_compliance_enabled BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS tenant_compliance_summaries (
    tenant_id UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    overall_score_percentage NUMERIC(5, 2) NOT NULL DEFAULT 0
        CHECK (overall_score_percentage >= 0 AND overall_score_percentage <= 100),
    passed_checks INTEGER NOT NULL DEFAULT 0 CHECK (passed_checks >= 0),
    failed_checks INTEGER NOT NULL DEFAULT 0 CHECK (failed_checks >= 0),
    total_checks INTEGER NOT NULL DEFAULT 0 CHECK (total_checks >= 0),
    agent_count INTEGER NOT NULL DEFAULT 0 CHECK (agent_count >= 0),
    policy_count INTEGER NOT NULL DEFAULT 0 CHECK (policy_count >= 0),
    framework_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_evaluated_at TIMESTAMPTZ,
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sync_status TEXT NOT NULL DEFAULT 'never'
        CHECK (sync_status IN ('never', 'ok', 'partial', 'error', 'empty')),
    sync_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sca_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    agent_name TEXT,
    policy_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    pass_count INTEGER NOT NULL DEFAULT 0 CHECK (pass_count >= 0),
    fail_count INTEGER NOT NULL DEFAULT 0 CHECK (fail_count >= 0),
    invalid_count INTEGER NOT NULL DEFAULT 0 CHECK (invalid_count >= 0),
    total_checks INTEGER NOT NULL DEFAULT 0 CHECK (total_checks >= 0),
    score NUMERIC(5, 2) NOT NULL DEFAULT 0
        CHECK (score >= 0 AND score <= 100),
    compliance_frameworks JSONB NOT NULL DEFAULT '[]'::jsonb,
    end_scan_at TIMESTAMPTZ,
    raw_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, agent_id, policy_id)
);

CREATE INDEX IF NOT EXISTS idx_sca_evaluations_tenant_score
    ON sca_evaluations (tenant_id, score ASC, updated_at DESC);

CREATE TABLE IF NOT EXISTS sca_check_details (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id UUID NOT NULL REFERENCES sca_evaluations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    check_id TEXT NOT NULL,
    rule_title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL
        CHECK (status IN ('PASSED', 'FAILED', 'NOT_APPLICABLE', 'UNKNOWN')),
    severity TEXT NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info')),
    rationale TEXT NOT NULL DEFAULT '',
    remediation TEXT NOT NULL DEFAULT '',
    compliance_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (evaluation_id, check_id)
);

CREATE INDEX IF NOT EXISTS idx_sca_checks_tenant_status
    ON sca_check_details (tenant_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sca_checks_evaluation
    ON sca_check_details (evaluation_id, status);

DROP TRIGGER IF EXISTS trg_tenant_compliance_summaries_updated_at ON tenant_compliance_summaries;
CREATE TRIGGER trg_tenant_compliance_summaries_updated_at
BEFORE UPDATE ON tenant_compliance_summaries
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_sca_evaluations_updated_at ON sca_evaluations;
CREATE TRIGGER trg_sca_evaluations_updated_at
BEFORE UPDATE ON sca_evaluations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_sca_check_details_updated_at ON sca_check_details;
CREATE TRIGGER trg_sca_check_details_updated_at
BEFORE UPDATE ON sca_check_details
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
