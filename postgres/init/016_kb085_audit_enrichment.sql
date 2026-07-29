-- KB-085: Enrich audit_logs for portal audit trail (additive, non-destructive).

ALTER TABLE audit_logs
  ADD COLUMN IF NOT EXISTS actor_email TEXT,
  ADD COLUMN IF NOT EXISTS actor_role TEXT,
  ADD COLUMN IF NOT EXISTS action_status TEXT NOT NULL DEFAULT 'SUCCESS'
    CHECK (action_status IN ('SUCCESS', 'FAILED')),
  ADD COLUMN IF NOT EXISTS resource_type TEXT,
  ADD COLUMN IF NOT EXISTS resource_id TEXT;

-- Backfill resource_* from legacy entity_* for existing rows.
UPDATE audit_logs
SET resource_type = COALESCE(resource_type, entity_type),
    resource_id = COALESCE(resource_id, entity_id::text)
WHERE resource_type IS NULL OR resource_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_created
  ON audit_logs(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_action
  ON audit_logs(action, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_email
  ON audit_logs(actor_email);
