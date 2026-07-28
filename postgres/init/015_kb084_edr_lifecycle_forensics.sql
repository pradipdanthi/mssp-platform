-- KB-084: EDR action lifecycle, forensics artifacts, telemetry process cache (additive).

-- Expand action types and statuses (drop old checks, add new).
ALTER TABLE edr_action_executions DROP CONSTRAINT IF EXISTS edr_action_executions_action_type_check;
ALTER TABLE edr_action_executions DROP CONSTRAINT IF EXISTS edr_action_executions_status_check;

ALTER TABLE edr_action_executions
  ADD COLUMN IF NOT EXISTS status_detail TEXT,
  ADD COLUMN IF NOT EXISTS callback_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS external_ref TEXT;

ALTER TABLE edr_action_executions
  ADD CONSTRAINT edr_action_executions_action_type_check
  CHECK (action_type IN (
    'ISOLATE_HOST', 'UNISOLATE_HOST', 'KILL_PROCESS', 'COLLECT_FORENSICS', 'BLOCK_HASH'
  ));

ALTER TABLE edr_action_executions
  ADD CONSTRAINT edr_action_executions_status_check
  CHECK (status IN (
    'pending', 'executing', 'success', 'failed', 'verified',
    -- legacy aliases kept for rows written before KB-084
    'executed'
  ));

-- Normalize legacy executed -> success for new readers (keep value; API maps both).

CREATE TABLE IF NOT EXISTS edr_forensic_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    execution_id UUID REFERENCES edr_action_executions(id) ON DELETE SET NULL,
    agent_id TEXT,
    object_key TEXT NOT NULL,
    file_name TEXT,
    file_size_bytes BIGINT,
    sha256 TEXT,
    content_type TEXT DEFAULT 'application/zip',
    storage_backend TEXT NOT NULL DEFAULT 'local'
        CHECK (storage_backend IN ('local', 's3', 'azure', 'minio')),
    status TEXT NOT NULL DEFAULT 'awaiting_upload'
        CHECK (status IN ('awaiting_upload', 'uploaded', 'failed', 'expired')),
    upload_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_edr_forensics_tenant_created
  ON edr_forensic_artifacts(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_edr_forensics_execution
  ON edr_forensic_artifacts(execution_id);

-- Normalized process telemetry extracted from raw alerts (additive cache).
CREATE TABLE IF NOT EXISTS edr_process_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    alert_id UUID REFERENCES security_alerts(id) ON DELETE CASCADE,
    agent_id TEXT,
    pid INT,
    parent_pid INT,
    process_guid TEXT,
    parent_process_guid TEXT,
    process_name TEXT,
    parent_process_name TEXT,
    command_line TEXT,
    parent_command_line TEXT,
    username TEXT,
    hash_md5 TEXT,
    hash_sha256 TEXT,
    signed_status TEXT,
    event_time TIMESTAMPTZ,
    mitre_techniques JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_edr_process_events_tenant_alert
  ON edr_process_events(tenant_id, alert_id);

CREATE INDEX IF NOT EXISTS idx_edr_process_events_guid
  ON edr_process_events(tenant_id, process_guid);

ALTER TABLE edr_endpoint_isolation
  ADD COLUMN IF NOT EXISTS released_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS isolation_status TEXT NOT NULL DEFAULT 'isolated'
    CHECK (isolation_status IN ('isolated', 'restored', 'unknown'));

DROP TRIGGER IF EXISTS trg_edr_forensic_artifacts_updated_at ON edr_forensic_artifacts;
CREATE TRIGGER trg_edr_forensic_artifacts_updated_at
BEFORE UPDATE ON edr_forensic_artifacts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
