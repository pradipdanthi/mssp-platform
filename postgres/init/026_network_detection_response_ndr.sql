-- Network Detection & Response (NDR) — sensors + network threat events.
-- Idempotent for live apply.

CREATE TABLE IF NOT EXISTS tenant_ndr_sensors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    sensor_name TEXT NOT NULL,
    interface_ip INET,
    sensor_status TEXT NOT NULL DEFAULT 'ONLINE'
        CHECK (sensor_status IN ('ONLINE', 'DEGRADED', 'OFFLINE')),
    sensor_type TEXT NOT NULL DEFAULT 'SURICATA_ZEEK_HYBRID'
        CHECK (sensor_type IN ('SURICATA_ZEEK_HYBRID', 'SIGNATURE', 'METADATA')),
    capture_interface TEXT,
    flows_observed BIGINT NOT NULL DEFAULT 0 CHECK (flows_observed >= 0),
    bytes_observed BIGINT NOT NULL DEFAULT 0 CHECK (bytes_observed >= 0),
    last_heartbeat TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, sensor_name)
);

CREATE INDEX IF NOT EXISTS idx_tenant_ndr_sensors_tenant
    ON tenant_ndr_sensors (tenant_id, sensor_status);

CREATE TABLE IF NOT EXISTS tenant_ndr_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    sensor_id UUID REFERENCES tenant_ndr_sensors(id) ON DELETE SET NULL,
    source_ip INET,
    source_port INTEGER CHECK (source_port IS NULL OR (source_port >= 0 AND source_port <= 65535)),
    destination_ip INET,
    destination_port INTEGER CHECK (destination_port IS NULL OR (destination_port >= 0 AND destination_port <= 65535)),
    protocol TEXT NOT NULL
        CHECK (protocol IN ('DNS', 'HTTP', 'TLS', 'SSH', 'TCP', 'UDP', 'SMB', 'ICMP', 'OTHER')),
    event_category TEXT NOT NULL
        CHECK (event_category IN (
            'LATERAL_MOVEMENT',
            'C2_BEACONING',
            'DNS_TUNNELING',
            'EXPLOIT_ATTEMPT',
            'SUSPICIOUS_TRAFFIC',
            'TLS_RISK',
            'PORT_SCAN'
        )),
    severity TEXT NOT NULL
        CHECK (severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    signature_title TEXT NOT NULL DEFAULT '',
    mitre_technique TEXT,
    flow_bytes BIGINT NOT NULL DEFAULT 0 CHECK (flow_bytes >= 0),
    summary TEXT NOT NULL DEFAULT '',
    remediation TEXT NOT NULL DEFAULT '',
    source_endpoint_label TEXT NOT NULL DEFAULT 'Internal endpoint',
    destination_endpoint_label TEXT NOT NULL DEFAULT 'Network destination',
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'acknowledged', 'resolved')),
    raw_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_ndr_events_tenant_sev
    ON tenant_ndr_events (tenant_id, severity, status, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenant_ndr_events_category
    ON tenant_ndr_events (tenant_id, event_category, detected_at DESC);

DROP TRIGGER IF EXISTS trg_tenant_ndr_sensors_updated_at ON tenant_ndr_sensors;
CREATE TRIGGER trg_tenant_ndr_sensors_updated_at
BEFORE UPDATE ON tenant_ndr_sensors
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tenant_ndr_events_updated_at ON tenant_ndr_events;
CREATE TRIGGER trg_tenant_ndr_events_updated_at
BEFORE UPDATE ON tenant_ndr_events
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
