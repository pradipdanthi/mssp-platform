-- 120: durable investigation job queue (replaces pop-before-process Redis list as the system of record).
--
-- Additive only. Rolling application code back leaves this table in place and harmless; the
-- legacy Redis path keeps working until this migration is applied.
--
-- Semantics worth stating once:
--   * A job is ACCEPTED when its row is committed. A crash afterwards cannot lose it.
--   * claim = take a time-limited lease (state running, lease_expires_at). A worker that dies
--     leaves an expired lease; recover_expired() makes the job claimable again and counts the attempt.
--   * Delivery is AT LEAST ONCE. The investigation is idempotent because every attempt is bound to
--     (alert, evidence version, attempt number) in tia_investigation_attempts and results are
--     immutable and unique per attempt. This is NOT an exactly-once claim.
--   * A failed job is rescheduled with next_run_at (backoff). Other jobs are never blocked by it.
--   * At most one live (queued or running) job per (kind, alert): enqueue is idempotent.
--   * No row-level security: the table holds identifiers, timings and error CATEGORIES only, is read
--     by the system worker, and is exposed to staff only as aggregate counts.

CREATE TABLE IF NOT EXISTS tia_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind TEXT NOT NULL DEFAULT 'alert_analysis',
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    alert_id UUID NOT NULL REFERENCES security_alerts(id) ON DELETE CASCADE,
    priority SMALLINT NOT NULL DEFAULT 2,                  -- 0 critical, 1 high, 2 other
    state TEXT NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued', 'running', 'succeeded', 'dead', 'cancelled')),
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 4,
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    last_error_category TEXT,                              -- category only, never provider text
    dead_reason TEXT,
    requeues INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'ingest',                 -- ingest | sweeper | legacy_redis | requeue
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tia_jobs_live
    ON tia_jobs (kind, alert_id) WHERE state IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS idx_tia_jobs_claim ON tia_jobs (priority, next_run_at) WHERE state = 'queued';
CREATE INDEX IF NOT EXISTS idx_tia_jobs_lease ON tia_jobs (lease_expires_at) WHERE state = 'running';
CREATE INDEX IF NOT EXISTS idx_tia_jobs_tenant_state ON tia_jobs (tenant_id, state);
CREATE INDEX IF NOT EXISTS idx_tia_jobs_alert ON tia_jobs (alert_id, created_at DESC);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mssp_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON tia_jobs TO mssp_app;
    END IF;
END
$$;

COMMENT ON TABLE tia_jobs IS
    'Durable investigation jobs. At-least-once delivery; effects are idempotent via tia_investigation_attempts.';

INSERT INTO tia_schema_version (component, version) VALUES ('tia_jobs', 120)
ON CONFLICT (component) DO UPDATE SET version = GREATEST(tia_schema_version.version, EXCLUDED.version);
