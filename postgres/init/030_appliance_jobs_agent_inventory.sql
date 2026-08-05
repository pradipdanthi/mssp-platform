-- Appliance Track-1: job queue for cloud→appliance commands (isolate/AR)
-- and explicit enabled_services column for Admin visibility.
-- Additive only — never drops existing objects.

CREATE TABLE IF NOT EXISTS appliance_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appliance_id UUID NOT NULL REFERENCES appliances(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'dispatched', 'executing', 'success', 'failed', 'expired', 'cancelled')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB,
    edr_execution_id UUID,
    requested_by_user_id UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    dispatched_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '24 hours')
);

CREATE INDEX IF NOT EXISTS idx_appliance_jobs_appliance_pending
    ON appliance_jobs (appliance_id, status, created_at)
    WHERE status IN ('pending', 'dispatched');

CREATE INDEX IF NOT EXISTS idx_appliance_jobs_tenant
    ON appliance_jobs (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_appliance_jobs_edr_execution
    ON appliance_jobs (edr_execution_id)
    WHERE edr_execution_id IS NOT NULL;

ALTER TABLE appliances
    ADD COLUMN IF NOT EXISTS enabled_services TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON TABLE appliance_jobs IS
    'Cloud→appliance command queue (Phase A pull via heartbeat). Isolate/AR for appliance tenants.';
COMMENT ON COLUMN appliances.enabled_services IS
    'Catalogue svc-01..10 currently enabled; synced from heartbeat.';
