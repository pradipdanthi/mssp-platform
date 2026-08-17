-- KB-103: Controlled service rollout (order number, confirmation email, asset scope).

ALTER TABLE tenant_asset_service_coverage
  DROP CONSTRAINT IF EXISTS tenant_asset_service_coverage_service_key_check;

ALTER TABLE tenant_asset_service_coverage
  ADD CONSTRAINT tenant_asset_service_coverage_service_key_check
  CHECK (service_key IN (
    'log_event_monitoring',
    'incident_response',
    'security_automation',
    'vulnerability_management',
    'continuous_compliance',
    'network_detection_response',
    'network_traffic_analysis',
    'threat_intelligence',
    'endpoint_forensics_deception',
    'endpoint_forensics',
    'external_attack_surface',
    'cloud_identity_protection',
    'other'
  ));

CREATE TABLE IF NOT EXISTS service_rollout_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    service_key TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('enable', 'disable')),
    scope TEXT NOT NULL CHECK (scope IN ('account', 'assets')),
    customer_order_number TEXT NOT NULL,
    confirmation_email TEXT NOT NULL,
    asset_ids UUID[] NOT NULL DEFAULT '{}',
    requested_by_user_id UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    admin_notes TEXT,
    jobs_queued INTEGER NOT NULL DEFAULT 0,
    email_dispatched_at TIMESTAMPTZ,
    email_dispatch_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_service_rollout_orders_tenant
  ON service_rollout_orders (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_service_rollout_orders_order_number
  ON service_rollout_orders (customer_order_number);
