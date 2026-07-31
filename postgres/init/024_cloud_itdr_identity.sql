-- Cloud & Identity Threat Protection (ITDR) — M365/Entra identity monitoring.
-- Idempotent for live apply.

ALTER TABLE tenant_entitlements
    ADD COLUMN IF NOT EXISTS cloud_identity_protection_enabled BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS tenant_cloud_identity_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider TEXT NOT NULL
        CHECK (provider IN ('M365_ENTRA', 'AWS_IAM', 'GCP_IAM')),
    tenant_domain TEXT NOT NULL,
    display_name TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING_AUTH'
        CHECK (status IN ('CONNECTED', 'PENDING_AUTH', 'DISCONNECTED')),
    monitored_seat_count INTEGER NOT NULL DEFAULT 0 CHECK (monitored_seat_count >= 0),
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, provider, tenant_domain)
);

CREATE INDEX IF NOT EXISTS idx_cloud_identity_configs_tenant
    ON tenant_cloud_identity_configs (tenant_id, status);

CREATE TABLE IF NOT EXISTS tenant_cloud_identity_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    config_id UUID REFERENCES tenant_cloud_identity_configs(id) ON DELETE SET NULL,
    user_principal_name TEXT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'IMPOSSIBLE_TRAVEL',
            'MFA_BYPASS_ATTEMPT',
            'ROGUE_ADMIN_ASSIGNED',
            'EXTERNAL_MAIL_FORWARDING',
            'SUSPICIOUS_LOGIN'
        )),
    severity TEXT NOT NULL
        CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    source_ip INET,
    location_country TEXT,
    location_city TEXT,
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    remediation TEXT NOT NULL DEFAULT '',
    raw_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'acknowledged', 'resolved')),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cloud_identity_events_tenant_sev
    ON tenant_cloud_identity_events (tenant_id, severity, status, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_cloud_identity_events_user
    ON tenant_cloud_identity_events (tenant_id, user_principal_name, detected_at DESC);

DROP TRIGGER IF EXISTS trg_tenant_cloud_identity_configs_updated_at ON tenant_cloud_identity_configs;
CREATE TRIGGER trg_tenant_cloud_identity_configs_updated_at
BEFORE UPDATE ON tenant_cloud_identity_configs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tenant_cloud_identity_events_updated_at ON tenant_cloud_identity_events;
CREATE TRIGGER trg_tenant_cloud_identity_events_updated_at
BEFORE UPDATE ON tenant_cloud_identity_events
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
