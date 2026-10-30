-- 121: verified playbooks for closure of alerts that are provably expected activity.
--
-- Additive only. No row exists after this migration, so NOTHING is enabled and no alert can be
-- closed by a playbook until a customer-authorised enablement row is created by a human.
-- A model verdict or confidence never reaches these tables as an authorisation.
--
--   tia_authorized_activity     customer/SOC-approved activity windows (e.g. an approved scanner IP),
--                               each with an approver, a change reference and a validity window.
--   tia_playbook_enablements    per tenant, per playbook VERSION, who enabled it and when. One live row
--                               per (tenant, playbook). Disabling sets disabled_at; history is kept.
--   tia_playbook_evaluations    every evaluation (shadow or enforced) with outcome, reasons and an
--                               evidence hash. Unique per (alert, playbook, version, evidence hash), so
--                               a repeated delivery re-uses the same row. reviewer_label records the
--                               human judgement used to measure the playbook before it is enforced.

CREATE TABLE IF NOT EXISTS tia_authorized_activity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('scanner')),
    source_ip INET NOT NULL,
    label TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ NOT NULL,
    approved_by TEXT NOT NULL CHECK (length(btrim(approved_by)) > 0),
    reference TEXT NOT NULL CHECK (length(btrim(reference)) > 0),
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to > valid_from)
);
CREATE INDEX IF NOT EXISTS idx_tia_authorized_activity_lookup ON tia_authorized_activity (tenant_id, kind, source_ip);

CREATE TABLE IF NOT EXISTS tia_playbook_enablements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    playbook_id TEXT NOT NULL,
    playbook_version INTEGER NOT NULL,
    enabled_by TEXT NOT NULL CHECK (length(btrim(enabled_by)) > 0),
    customer_authorisation TEXT NOT NULL CHECK (length(btrim(customer_authorisation)) > 0),
    enabled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    disabled_at TIMESTAMPTZ,
    disabled_by TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tia_playbook_enablements_live
    ON tia_playbook_enablements (tenant_id, playbook_id) WHERE disabled_at IS NULL;

CREATE TABLE IF NOT EXISTS tia_playbook_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    alert_id UUID NOT NULL REFERENCES security_alerts(id) ON DELETE CASCADE,
    playbook_id TEXT NOT NULL,
    playbook_version INTEGER NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('close', 'refuse', 'review')),
    disposition TEXT NOT NULL DEFAULT 'authorized_benign' CHECK (disposition IN ('false_positive', 'authorized_benign')),
    mode TEXT NOT NULL CHECK (mode IN ('shadow', 'enforced')),
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_hash TEXT NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    executed_at TIMESTAMPTZ,
    executed_verified BOOLEAN,
    reopened_at TIMESTAMPTZ,
    reopen_reason TEXT,
    reviewer_label TEXT CHECK (reviewer_label IN ('agree', 'disagree')),
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    UNIQUE (alert_id, playbook_id, playbook_version, evidence_hash)
);
CREATE INDEX IF NOT EXISTS idx_tia_playbook_evaluations_tenant ON tia_playbook_evaluations (tenant_id, evaluated_at DESC);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mssp_app') THEN
        GRANT SELECT, INSERT, UPDATE ON tia_authorized_activity, tia_playbook_enablements, tia_playbook_evaluations TO mssp_app;
    END IF;
END
$$;

COMMENT ON TABLE tia_playbook_enablements IS
    'Empty by default: no playbook may close anything until a human records customer authorisation here.';

INSERT INTO tia_schema_version (component, version) VALUES ('tia_playbooks', 121)
ON CONFLICT (component) DO UPDATE SET version = GREATEST(tia_schema_version.version, EXCLUDED.version);
