-- KB-083: EDR action audit, endpoint isolation state, telemetry counters (additive).

CREATE TABLE IF NOT EXISTS edr_action_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
    alert_id UUID REFERENCES security_alerts(id) ON DELETE SET NULL,
    requested_by_user_id UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    action_type TEXT NOT NULL
        CHECK (action_type IN ('ISOLATE_HOST', 'KILL_PROCESS', 'COLLECT_FORENSICS', 'BLOCK_HASH')),
    target_agent_id TEXT,
    target_pid TEXT,
    target_hash TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'executed', 'failed')),
    result_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_edr_actions_tenant_created
    ON edr_action_executions(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_edr_actions_incident
    ON edr_action_executions(incident_id);

CREATE TABLE IF NOT EXISTS edr_endpoint_isolation (
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    isolated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    isolated_by_user_id UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    PRIMARY KEY (tenant_id, agent_id)
);

CREATE TABLE IF NOT EXISTS edr_telemetry_stats (
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    stat_date DATE NOT NULL DEFAULT CURRENT_DATE,
    events_processed BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, stat_date)
);

DROP TRIGGER IF EXISTS trg_edr_action_executions_updated_at ON edr_action_executions;
CREATE TRIGGER trg_edr_action_executions_updated_at
BEFORE UPDATE ON edr_action_executions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
