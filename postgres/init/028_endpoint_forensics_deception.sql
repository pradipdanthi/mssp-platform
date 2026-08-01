-- Endpoint Forensics & Deception (Phase 7).
-- Idempotent for live apply. No third-party product names in customer-facing columns.

CREATE TABLE IF NOT EXISTS tenant_deception_tripwires (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    tripwire_name TEXT NOT NULL,
    tripwire_type TEXT NOT NULL
        CHECK (tripwire_type IN (
            'DECOY_CREDENTIAL', 'FAKE_SHARE', 'HONEYPOT_SERVICE', 'CANARY_TOKEN', 'BAIT_FILE'
        )),
    host_label TEXT NOT NULL DEFAULT 'Managed endpoint',
    deployment_status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (deployment_status IN ('ACTIVE', 'PAUSED', 'RETIRED')),
    sensitivity TEXT NOT NULL DEFAULT 'HIGH'
        CHECK (sensitivity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    auto_isolate_on_trip BOOLEAN NOT NULL DEFAULT TRUE,
    summary TEXT NOT NULL DEFAULT '',
    planted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, tripwire_name)
);

CREATE INDEX IF NOT EXISTS idx_tenant_deception_tripwires_tenant
    ON tenant_deception_tripwires (tenant_id, deployment_status, planted_at DESC);

CREATE TABLE IF NOT EXISTS tenant_deception_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    tripwire_id UUID REFERENCES tenant_deception_tripwires(id) ON DELETE SET NULL,
    event_title TEXT NOT NULL,
    severity TEXT NOT NULL
        CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    actor_label TEXT NOT NULL DEFAULT 'Unknown actor',
    host_label TEXT NOT NULL DEFAULT 'Managed endpoint',
    isolation_status TEXT NOT NULL DEFAULT 'NOT_REQUESTED'
        CHECK (isolation_status IN (
            'NOT_REQUESTED', 'REQUESTED', 'ISOLATED', 'FAILED', 'NOT_APPLICABLE'
        )),
    summary TEXT NOT NULL DEFAULT '',
    recommended_action TEXT NOT NULL DEFAULT '',
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'investigating', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_deception_events_tenant
    ON tenant_deception_events (tenant_id, status, severity, detected_at DESC);

CREATE TABLE IF NOT EXISTS tenant_forensics_collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    collection_name TEXT NOT NULL,
    host_label TEXT NOT NULL DEFAULT 'Managed endpoint',
    collection_scope TEXT NOT NULL DEFAULT 'TRIAGE'
        CHECK (collection_scope IN ('TRIAGE', 'MEMORY', 'DISK_ARTIFACTS', 'PROCESS_TREE', 'FULL')),
    status TEXT NOT NULL DEFAULT 'READY'
        CHECK (status IN ('QUEUED', 'RUNNING', 'READY', 'EXPIRED', 'FAILED')),
    package_size_bytes BIGINT NOT NULL DEFAULT 0 CHECK (package_size_bytes >= 0),
    download_available BOOLEAN NOT NULL DEFAULT FALSE,
    summary TEXT NOT NULL DEFAULT '',
    related_event_title TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, collection_name)
);

CREATE INDEX IF NOT EXISTS idx_tenant_forensics_collections_tenant
    ON tenant_forensics_collections (tenant_id, status, requested_at DESC);

DROP TRIGGER IF EXISTS trg_tenant_deception_tripwires_updated_at ON tenant_deception_tripwires;
CREATE TRIGGER trg_tenant_deception_tripwires_updated_at
BEFORE UPDATE ON tenant_deception_tripwires
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tenant_deception_events_updated_at ON tenant_deception_events;
CREATE TRIGGER trg_tenant_deception_events_updated_at
BEFORE UPDATE ON tenant_deception_events
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tenant_forensics_collections_updated_at ON tenant_forensics_collections;
CREATE TRIGGER trg_tenant_forensics_collections_updated_at
BEFORE UPDATE ON tenant_forensics_collections
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
