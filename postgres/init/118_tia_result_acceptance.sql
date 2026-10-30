-- TIA repair increment 2: unified result acceptance, review lifecycle, and a
-- notification outbox with explicit delivery states.
--
-- ADDITIVE ONLY. Requires 117_tia_review_items.sql. Safe to re-run.
-- Never drops or rewrites existing review records. Apply with psql in a
-- reviewed change window; it is not applied automatically to a running database.
--
-- Rollback keeps every table and row (history is retained); see
-- docs/TIA_INVESTIGATION_STATUS.md for the manual-review mode.

DO $$
BEGIN
    IF to_regclass('public.tia_review_items') IS NULL THEN
        RAISE EXCEPTION 'tia_review_items missing: apply 117_tia_review_items.sql before 118';
    END IF;
END
$$;

-- ---------------------------------------------------------------------
-- Review items: ownership, lifecycle, provisional-deadline marker.
-- Existing rows keep their values; new columns take safe defaults.
-- ---------------------------------------------------------------------
ALTER TABLE tia_review_items
    ADD COLUMN IF NOT EXISTS assigned_to TEXT,
    ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reopened_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS reopened_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS evidence_version TEXT,
    ADD COLUMN IF NOT EXISTS highest_finding TEXT,
    ADD COLUMN IF NOT EXISTS analysis_available BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS resolution_note TEXT,
    -- Deadlines are provisional until the SOC owner approves them; never an SLA.
    ADD COLUMN IF NOT EXISTS deadline_basis TEXT NOT NULL DEFAULT 'provisional';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tia_review_items_deadline_basis_chk'
    ) THEN
        ALTER TABLE tia_review_items
            ADD CONSTRAINT tia_review_items_deadline_basis_chk
            CHECK (deadline_basis IN ('provisional', 'approved'));
    END IF;
END
$$;

-- ---------------------------------------------------------------------
-- Review history (append-only audit of every transition)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tia_review_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    review_item_id UUID NOT NULL REFERENCES tia_review_items(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    from_status TEXT,
    to_status TEXT,
    attempt_id UUID,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- clock_timestamp so events written in one transaction keep their order
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS idx_tia_review_events_item
    ON tia_review_events (review_item_id, created_at);

-- Items that already exist get a creation event so history is complete.
INSERT INTO tia_review_events (tenant_id, review_item_id, event_type, actor, to_status, detail, created_at)
SELECT r.tenant_id, r.id, 'created', 'system:migration_118', r.status,
       jsonb_build_object('backfilled', true, 'reason_code', r.reason_code), r.first_seen_at
FROM tia_review_items r
WHERE NOT EXISTS (SELECT 1 FROM tia_review_events e WHERE e.review_item_id = r.id);

-- ---------------------------------------------------------------------
-- Investigation attempts: the job / attempt / evidence-version binding
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tia_investigation_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    alert_id UUID NOT NULL REFERENCES security_alerts(id) ON DELETE CASCADE,
    evidence_version TEXT NOT NULL,
    job_key TEXT NOT NULL,
    attempt_no INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'dispatched'
        CHECK (status IN ('dispatched', 'result_received', 'transport_failed', 'timed_out', 'abandoned')),
    -- true while the remote investigation may still be running (HTTP timeout
    -- does not prove it stopped); a late result is still accepted.
    outcome_uncertain BOOLEAN NOT NULL DEFAULT false,
    transport_error TEXT,
    dispatched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    accept_until TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,
    UNIQUE (alert_id, evidence_version, attempt_no)
);
CREATE INDEX IF NOT EXISTS idx_tia_attempts_alert ON tia_investigation_attempts (alert_id, dispatched_at DESC);
CREATE INDEX IF NOT EXISTS idx_tia_attempts_open
    ON tia_investigation_attempts (dispatched_at) WHERE status = 'dispatched';

-- ---------------------------------------------------------------------
-- Accepted results: one immutable row per attempt
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tia_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id UUID NOT NULL UNIQUE REFERENCES tia_investigation_attempts(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    alert_id UUID NOT NULL REFERENCES security_alerts(id) ON DELETE CASCADE,
    evidence_version TEXT NOT NULL,
    first_source TEXT NOT NULL CHECK (first_source IN ('http', 'callback', 'local')),
    payload_hash TEXT NOT NULL,
    execution_status TEXT NOT NULL
        CHECK (execution_status IN ('succeeded', 'degraded', 'failed', 'timed_out')),
    error_category TEXT,
    verdict TEXT,
    confidence NUMERIC(5, 2),
    disposition TEXT NOT NULL DEFAULT 'unset',
    outcome JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- applied = written to the authoritative alert fields. Stale, superseded,
    -- or human-decided results are kept here as history but not applied.
    applied BOOLEAN NOT NULL DEFAULT false,
    apply_reason TEXT NOT NULL,
    material BOOLEAN NOT NULL DEFAULT false,
    late BOOLEAN NOT NULL DEFAULT false,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tia_results_alert ON tia_results (alert_id, accepted_at DESC);

CREATE OR REPLACE FUNCTION tia_results_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'tia_results rows are immutable (id %)', OLD.id;
END
$$;

DROP TRIGGER IF EXISTS trg_tia_results_immutable ON tia_results;
CREATE TRIGGER trg_tia_results_immutable
    BEFORE UPDATE ON tia_results
    FOR EACH ROW EXECUTE FUNCTION tia_results_immutable();

-- ---------------------------------------------------------------------
-- Acceptance log: every delivery, including duplicates and rejections
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tia_acceptance_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID,
    alert_id UUID,
    attempt_id UUID,
    source TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('accepted', 'duplicate', 'conflict', 'rejected')),
    reason TEXT,
    payload_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tia_acceptance_log_attempt ON tia_acceptance_log (attempt_id, created_at);

-- ---------------------------------------------------------------------
-- Notification outbox with explicit delivery states
--   required   obligation recorded in the same transaction as the decision
--   queued     claimed by the dispatcher (leased) for a send attempt
--   submitted  the provider accepted the message (NOT proof a person saw it)
--   delivered  the provider reported a delivery receipt
--   failed     attempts exhausted or a permanent error
--   acknowledged  an authenticated analyst took responsibility
--   cancelled  no longer needed (analyst acknowledged before it was sent)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tia_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    alert_id UUID REFERENCES security_alerts(id) ON DELETE CASCADE,
    review_item_id UUID REFERENCES tia_review_items(id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN ('page', 'outage_notice')),
    level INTEGER NOT NULL DEFAULT 1,
    base_key TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    channel TEXT NOT NULL,
    -- NULL until a recipient is configured; the row then shows a visible fault.
    recipient_address TEXT,
    recipient_name TEXT,
    message_body TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'required'
        CHECK (state IN ('required', 'queued', 'submitted', 'delivered', 'failed', 'acknowledged', 'cancelled')),
    blocked_reason TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 4,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_until TIMESTAMPTZ,
    last_error TEXT,
    provider TEXT,
    provider_message_id TEXT,
    delivery_evidence TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    queued_at TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by TEXT,
    -- When an acknowledgement is overdue the dispatcher raises the next level.
    ack_due_at TIMESTAMPTZ,
    escalated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_tia_notifications_work
    ON tia_notifications (next_attempt_at) WHERE state IN ('required', 'queued');
CREATE INDEX IF NOT EXISTS idx_tia_notifications_base ON tia_notifications (base_key);
CREATE INDEX IF NOT EXISTS idx_tia_notifications_item ON tia_notifications (review_item_id);
CREATE INDEX IF NOT EXISTS idx_tia_notifications_provider_msg
    ON tia_notifications (provider_message_id) WHERE provider_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tia_notifications_ack
    ON tia_notifications (ack_due_at)
    WHERE kind = 'page' AND escalated_at IS NULL AND state NOT IN ('acknowledged', 'cancelled');

-- ---------------------------------------------------------------------
-- Row-level security + grants (same pattern as 117)
-- ---------------------------------------------------------------------
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'tia_review_events', 'tia_investigation_attempts', 'tia_results', 'tia_notifications'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_tenant_isolation', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I FOR ALL USING (app_rls_tenant_visible(tenant_id)) '
            'WITH CHECK (app_rls_tenant_visible(tenant_id))',
            t || '_tenant_isolation', t
        );
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mssp_app') THEN
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO mssp_app', t);
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mssp_app') THEN
        GRANT SELECT, INSERT ON tia_acceptance_log TO mssp_app;
    END IF;
END
$$;

COMMENT ON TABLE tia_notifications IS
    'Outbox for TIA pages. state=submitted means provider-accepted only; delivered needs a provider receipt; acknowledged needs an analyst action.';
COMMENT ON TABLE tia_results IS
    'Immutable accepted investigation results, one per attempt. History is never overwritten.';

-- Marker consumed by the application readiness check.
CREATE TABLE IF NOT EXISTS tia_schema_version (
    component TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO tia_schema_version (component, version) VALUES ('tia', 118)
ON CONFLICT (component) DO UPDATE SET version = GREATEST(tia_schema_version.version, EXCLUDED.version);
