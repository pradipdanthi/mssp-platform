-- Service catalog consulting / upgrade requests (dual-portal catalog).
-- Idempotent for live apply.

CREATE TABLE IF NOT EXISTS service_consultation_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    requested_by_user_id UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    submitted_by_admin_user_id UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    service_key TEXT NOT NULL
        CHECK (service_key IN (
            'log_event_monitoring',
            'incident_response',
            'security_automation',
            'vulnerability_management',
            'continuous_compliance',
            'network_detection_response',
            'threat_intelligence',
            'endpoint_forensics_deception',
            'external_attack_surface',
            'cloud_identity_protection',
            'other'
        )),
    service_name TEXT NOT NULL,
    pricing_tier TEXT,
    endpoint_count INTEGER
        CHECK (endpoint_count IS NULL OR (endpoint_count >= 0 AND endpoint_count <= 1000000)),
    m365_seat_count INTEGER
        CHECK (m365_seat_count IS NULL OR (m365_seat_count >= 0 AND m365_seat_count <= 1000000)),
    target_domains TEXT[] NOT NULL DEFAULT '{}',
    scope_notes TEXT NOT NULL DEFAULT '',
    contact_name TEXT,
    contact_email TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING_CONSULTATION'
        CHECK (status IN (
            'PENDING_CONSULTATION',
            'UNDER_REVIEW',
            'APPROVED',
            'PROVISIONED',
            'DECLINED',
            'CLOSED'
        )),
    admin_notes TEXT,
    email_dispatched_at TIMESTAMPTZ,
    email_dispatch_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_service_consultation_tenant_created
    ON service_consultation_requests (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_consultation_status
    ON service_consultation_requests (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_consultation_pending
    ON service_consultation_requests (created_at DESC)
    WHERE status IN ('PENDING_CONSULTATION', 'UNDER_REVIEW');

DROP TRIGGER IF EXISTS trg_service_consultation_requests_updated_at ON service_consultation_requests;
CREATE TRIGGER trg_service_consultation_requests_updated_at
BEFORE UPDATE ON service_consultation_requests
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
