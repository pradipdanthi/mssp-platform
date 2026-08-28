-- NikTiar ThreatLens + Retrospective Engine (universal appliance + cloud).
-- Note: prompt filename 025_* was already used by VMaaS — this is the live migration id.
-- Idempotent for live apply.

-- Appliance telemetry columns (source of truth remains appliances)
ALTER TABLE appliances
    ADD COLUMN IF NOT EXISTS disk_used_gb NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS log_ingest_rate NUMERIC(12, 2);

-- Compatibility projection matching the ThreatLens architecture contract
CREATE OR REPLACE VIEW tenant_appliances AS
SELECT
    a.id,
    a.tenant_id,
    COALESCE(NULLIF(a.appliance_uuid, ''), a.id::text) AS appliance_ref,
    host(a.local_ip) AS ip_address,
    CASE
        WHEN lower(a.status) = 'online' THEN 'ONLINE'
        ELSE 'OFFLINE'
    END AS status,
    a.disk_used_gb,
    a.log_ingest_rate,
    a.last_seen_at AS last_heartbeat
FROM appliances a
WHERE a.status IS DISTINCT FROM 'retired';

CREATE TABLE IF NOT EXISTS retrospective_hunt_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    appliance_id UUID REFERENCES appliances(id) ON DELETE SET NULL,
    execution_mode TEXT NOT NULL
        CHECK (execution_mode IN ('LOCAL_APPLIANCE', 'CLOUD_SOC')),
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),
    lookback_days INTEGER NOT NULL DEFAULT 90
        CHECK (lookback_days > 0 AND lookback_days <= 400),
    iocs JSONB NOT NULL DEFAULT '[]'::jsonb,
    matches_count INTEGER NOT NULL DEFAULT 0 CHECK (matches_count >= 0),
    matched_details JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message TEXT,
    source TEXT NOT NULL DEFAULT 'threatlens'
        CHECK (source IN ('threatlens', 'admin', 'stix_feed', 'api')),
    created_by UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_retro_hunt_tenant_created
    ON retrospective_hunt_jobs (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_retro_hunt_status
    ON retrospective_hunt_jobs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_retro_hunt_mode
    ON retrospective_hunt_jobs (execution_mode, status);

DROP TRIGGER IF EXISTS trg_retrospective_hunt_jobs_updated_at ON retrospective_hunt_jobs;
CREATE TRIGGER trg_retrospective_hunt_jobs_updated_at
BEFORE UPDATE ON retrospective_hunt_jobs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
