-- TIA repair increment 1: durable analyst review items.
--
-- A failed, timed-out, degraded, or model-flagged investigation must leave a
-- visible, durable record. It must never silently become a benign verdict and
-- must never disappear when a worker or notification step fails.
--
-- Additive only. Not applied automatically to a running database: apply with
-- psql during a reviewed change window (see docs/TIA_INVESTIGATION_STATUS.md).

CREATE TABLE IF NOT EXISTS tia_review_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    alert_id UUID NOT NULL REFERENCES security_alerts(id) ON DELETE CASCADE,
    -- why a person must look: investigation_failed | investigation_timed_out |
    -- investigation_degraded | model_requested_review | policy_required
    reason_code TEXT NOT NULL,
    execution_status TEXT NOT NULL
        CHECK (execution_status IN ('succeeded', 'degraded', 'failed', 'timed_out')),
    error_category TEXT,
    -- source severity as received; never rewritten by the model or this table
    source_severity TEXT,
    -- priority assessed by policy: P1 (urgent) .. P4
    assessed_priority TEXT NOT NULL
        CHECK (assessed_priority IN ('P1', 'P2', 'P3', 'P4')),
    -- 'page' = a notification was required; 'queue' = analyst queue only.
    -- Independent of whether a review is required.
    notify_urgency TEXT NOT NULL DEFAULT 'queue'
        CHECK (notify_urgency IN ('page', 'queue')),
    notification_state TEXT NOT NULL DEFAULT 'not_required',
    due_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'acknowledged', 'resolved')),
    model_review_requested BOOLEAN NOT NULL DEFAULT false,
    occurrences INTEGER NOT NULL DEFAULT 1,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    limited_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT
);

-- One live review item per alert: repeated attempts update it instead of
-- creating duplicates (idempotent under queue retries and the callback path).
CREATE UNIQUE INDEX IF NOT EXISTS uq_tia_review_items_alert_live
    ON tia_review_items (alert_id)
    WHERE status <> 'resolved';

CREATE INDEX IF NOT EXISTS idx_tia_review_items_open_due
    ON tia_review_items (status, due_at)
    WHERE status <> 'resolved';

CREATE INDEX IF NOT EXISTS idx_tia_review_items_tenant
    ON tia_review_items (tenant_id, status);

ALTER TABLE tia_review_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE tia_review_items FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tia_review_items_tenant_isolation ON tia_review_items;
CREATE POLICY tia_review_items_tenant_isolation ON tia_review_items
    FOR ALL
    USING (app_rls_tenant_visible(tenant_id))
    WITH CHECK (app_rls_tenant_visible(tenant_id));

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mssp_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON tia_review_items TO mssp_app;
    END IF;
END
$$;

COMMENT ON TABLE tia_review_items IS
    'Durable analyst review items for failed/degraded/flagged TIA investigations. Customer APIs must never read this table.';
