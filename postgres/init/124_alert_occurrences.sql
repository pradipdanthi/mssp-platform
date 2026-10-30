-- 124: occurrence merge for identical detections (same tenant, rule, host, behaviour).
-- Additive. Not applied automatically to a running database: apply with psql.
--
-- Audit / SLA rules encoded here:
--   * Every engine id is stored (never deleted).
--   * first_seen_at / created_at never move forward on merge (SLA clock stays).
--   * last_seen_at and occurrence_count record continuation.
--   * Closed / false_positive parents are NOT unique, so a later hit is a new alert.

ALTER TABLE security_alerts
    ADD COLUMN IF NOT EXISTS occurrence_count INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS merge_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS recurrence_of_alert_id UUID REFERENCES security_alerts(id) ON DELETE SET NULL;

UPDATE security_alerts
SET first_seen_at = COALESCE(first_seen_at, event_time, created_at),
    last_seen_at = COALESCE(last_seen_at, event_time, created_at)
WHERE first_seen_at IS NULL OR last_seen_at IS NULL;

ALTER TABLE security_alerts
    ALTER COLUMN first_seen_at SET DEFAULT now(),
    ALTER COLUMN last_seen_at SET DEFAULT now();

COMMENT ON COLUMN security_alerts.occurrence_count IS
    'How many identical engine events were merged into this open alert. SLA uses first_seen_at, not this counter.';
COMMENT ON COLUMN security_alerts.first_seen_at IS
    'Immutable SLA start for this open alert. Merge must never rewrite it.';
COMMENT ON COLUMN security_alerts.last_seen_at IS
    'Most recent identical occurrence. Does not reset first_seen_at or created_at.';
COMMENT ON COLUMN security_alerts.merge_fingerprint IS
    'Deterministic key: source|rule|host|behaviour. NULL means the event was not eligible to merge.';
COMMENT ON COLUMN security_alerts.recurrence_of_alert_id IS
    'Prior closed/false-positive alert this fingerprint reopened as a NEW obligation (new SLA clock).';

-- One live (open) parent per fingerprint. Closed rows are excluded so recurrence
-- after sign-off creates a new alert instead of silently absorbing.
CREATE UNIQUE INDEX IF NOT EXISTS uq_security_alerts_open_fingerprint
    ON security_alerts (tenant_id, merge_fingerprint)
    WHERE merge_fingerprint IS NOT NULL
      AND status IN ('new', 'triaged', 'incident_created');

CREATE INDEX IF NOT EXISTS idx_security_alerts_fingerprint
    ON security_alerts (tenant_id, merge_fingerprint)
    WHERE merge_fingerprint IS NOT NULL;

CREATE TABLE IF NOT EXISTS security_alert_occurrences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    alert_id UUID NOT NULL REFERENCES security_alerts(id) ON DELETE CASCADE,
    source_tool TEXT NOT NULL,
    external_alert_id TEXT NOT NULL,
    occurrence_no INTEGER NOT NULL CHECK (occurrence_no >= 1),
    event_time TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    severity TEXT,
    fingerprint TEXT,
    summary TEXT,
    UNIQUE (tenant_id, source_tool, external_alert_id)
);

CREATE INDEX IF NOT EXISTS idx_alert_occurrences_alert_no
    ON security_alert_occurrences (alert_id, occurrence_no);

COMMENT ON TABLE security_alert_occurrences IS
    'Immutable per-engine-event record under a merged SOC alert. Customer APIs must not list this table.';

ALTER TABLE security_alert_occurrences ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_alert_occurrences FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS security_alert_occurrences_tenant_isolation ON security_alert_occurrences;
CREATE POLICY security_alert_occurrences_tenant_isolation ON security_alert_occurrences
    FOR ALL
    USING (app_rls_tenant_visible(tenant_id))
    WITH CHECK (app_rls_tenant_visible(tenant_id));

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mssp_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON security_alert_occurrences TO mssp_app;
    END IF;
END
$$;

-- Seed occurrence #1 for existing alerts that have an engine id, so history is complete.
INSERT INTO security_alert_occurrences (
    tenant_id, alert_id, source_tool, external_alert_id,
    occurrence_no, event_time, received_at, severity, fingerprint, summary
)
SELECT
    sa.tenant_id,
    sa.id,
    sa.source_tool,
    sa.external_alert_id,
    1,
    COALESCE(sa.event_time, sa.created_at),
    sa.created_at,
    sa.severity,
    sa.merge_fingerprint,
    left(sa.alert_title, 500)
FROM security_alerts sa
WHERE sa.external_alert_id IS NOT NULL
  AND btrim(sa.external_alert_id) <> ''
ON CONFLICT (tenant_id, source_tool, external_alert_id) DO NOTHING;
