CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    short_code TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('onboarding', 'active', 'inactive', 'suspended')),
    sla_level TEXT NOT NULL DEFAULT 'standard'
        CHECK (sla_level IN ('standard', 'business', 'premium', '24x7')),
    business_criticality TEXT NOT NULL DEFAULT 'medium'
        CHECK (business_criticality IN ('low', 'medium', 'high', 'critical')),
    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS platform_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    user_type TEXT NOT NULL CHECK (user_type IN ('admin', 'customer')),
    role TEXT NOT NULL CHECK (role IN ('super_admin', 'soc_manager', 'soc_analyst', 'customer_admin', 'customer_viewer')),
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'locked')),
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenant_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    contact_type TEXT NOT NULL
        CHECK (contact_type IN ('primary', 'secondary', 'technical', 'security', 'billing', 'escalation')),
    full_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    whatsapp_number TEXT,
    whatsapp_opt_in BOOLEAN NOT NULL DEFAULT true,
    priority_order INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE TABLE IF NOT EXISTS appliance_activation_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    site_name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    token_hint TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'used', 'expired', 'revoked')),
    expires_at TIMESTAMPTZ,
    used_at TIMESTAMPTZ,
    created_by_user_id UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS appliances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    activation_token_id UUID REFERENCES appliance_activation_tokens(id) ON DELETE SET NULL,
    appliance_name TEXT NOT NULL,
    site_name TEXT NOT NULL,
    appliance_uuid TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'registered'
        CHECK (status IN ('registered', 'online', 'offline', 'maintenance', 'retired')),
    agent_version TEXT,
    config_version TEXT,
    git_commit TEXT,
    update_status TEXT DEFAULT 'unknown'
        CHECK (update_status IN ('unknown', 'current', 'update_available', 'updating', 'failed')),
    local_ip INET,
    last_source_ip INET,
    last_seen_at TIMESTAMPTZ,
    health_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, appliance_name)
);


CREATE TABLE IF NOT EXISTS protected_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    appliance_id UUID REFERENCES appliances(id) ON DELETE SET NULL,
    hostname TEXT,
    ip_address INET,
    asset_type TEXT NOT NULL DEFAULT 'server'
        CHECK (asset_type IN (
            'server', 'workstation', 'firewall', 'switch', 'load_balancer',
            'network_device', 'application', 'database', 'other'
        )),
    os_name TEXT,
    criticality TEXT NOT NULL DEFAULT 'medium'
        CHECK (criticality IN ('low', 'medium', 'high', 'critical')),
    owner TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'unknown')),
    last_seen_at TIMESTAMPTZ,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS appliance_heartbeats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appliance_id UUID NOT NULL REFERENCES appliances(id) ON DELETE CASCADE,
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_ip INET,
    agent_version TEXT,
    health_status TEXT NOT NULL DEFAULT 'unknown'
        CHECK (health_status IN ('healthy', 'warning', 'critical', 'unknown')),
    cpu_percent NUMERIC(5,2),
    memory_percent NUMERIC(5,2),
    disk_percent NUMERIC(5,2),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);


CREATE TABLE IF NOT EXISTS security_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    appliance_id UUID REFERENCES appliances(id) ON DELETE SET NULL,
    asset_id UUID REFERENCES protected_assets(id) ON DELETE SET NULL,
    source_tool TEXT NOT NULL,
    external_alert_id TEXT,
    severity TEXT NOT NULL
        CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    alert_title TEXT NOT NULL,
    alert_description TEXT,
    event_time TIMESTAMPTZ DEFAULT now(),
    source_ip INET,
    destination_ip INET,
    source_user TEXT,
    destination_host TEXT,
    raw_event JSONB NOT NULL DEFAULT '{}'::jsonb,
    ai_plain_summary TEXT,
    ai_technical_summary TEXT,
    ai_likely_attack_type TEXT,
    ai_business_impact TEXT,
    ai_recommended_action TEXT,
    ai_false_positive_score NUMERIC(5,2),
    mitre_mapping JSONB NOT NULL DEFAULT '{}'::jsonb,
    customer_visible BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'triaged', 'incident_created', 'false_positive', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    primary_alert_id UUID REFERENCES security_alerts(id) ON DELETE SET NULL,
    incident_number TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    severity TEXT NOT NULL
        CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'waiting_customer', 'resolved', 'closed')),
    assigned_to_user_id UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    customer_visible_summary TEXT,
    business_impact TEXT,
    customer_action_required TEXT,
    resolution_summary TEXT,
    internal_notes TEXT,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS incident_alerts (
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    alert_id UUID NOT NULL REFERENCES security_alerts(id) ON DELETE CASCADE,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (incident_id, alert_id)
);


CREATE TABLE IF NOT EXISTS incident_timeline (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('created', 'status_changed', 'assigned', 'comment', 'customer_update', 'notification', 'action_taken', 'resolved', 'closed')),
    visibility TEXT NOT NULL DEFAULT 'internal'
        CHECK (visibility IN ('internal', 'customer')),
    title TEXT NOT NULL,
    details TEXT,
    created_by_user_id UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS incident_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    created_by_user_id UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    visibility TEXT NOT NULL DEFAULT 'internal'
        CHECK (visibility IN ('internal', 'customer')),
    comment_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE TABLE IF NOT EXISTS notification_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
    alert_id UUID REFERENCES security_alerts(id) ON DELETE SET NULL,
    notification_type TEXT NOT NULL
        CHECK (notification_type IN ('whatsapp', 'email', 'sms', 'webhook')),
    recipient_name TEXT,
    recipient_address TEXT NOT NULL,
    message_body TEXT NOT NULL,
    provider TEXT,
    provider_message_id TEXT,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'sent', 'delivered', 'failed', 'acknowledged')),
    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS customer_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    related_alert_id UUID REFERENCES security_alerts(id) ON DELETE SET NULL,
    related_incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    category TEXT NOT NULL DEFAULT 'general',
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'accepted_risk', 'completed', 'dismissed')),
    customer_visible BOOLEAN NOT NULL DEFAULT true,
    due_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE TABLE IF NOT EXISTS monthly_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    report_month DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'published', 'archived')),
    executive_summary TEXT,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    report_file_path TEXT,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, report_month)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    actor_user_id UUID REFERENCES platform_users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,
    source_ip INET,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tenants_updated_at ON tenants;
CREATE TRIGGER trg_tenants_updated_at
BEFORE UPDATE ON tenants
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_platform_users_updated_at ON platform_users;
CREATE TRIGGER trg_platform_users_updated_at
BEFORE UPDATE ON platform_users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tenant_contacts_updated_at ON tenant_contacts;
CREATE TRIGGER trg_tenant_contacts_updated_at
BEFORE UPDATE ON tenant_contacts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_appliances_updated_at ON appliances;
CREATE TRIGGER trg_appliances_updated_at
BEFORE UPDATE ON appliances
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_protected_assets_updated_at ON protected_assets;
CREATE TRIGGER trg_protected_assets_updated_at
BEFORE UPDATE ON protected_assets
FOR EACH ROW EXECUTE FUNCTION set_updated_at();


DROP TRIGGER IF EXISTS trg_security_alerts_updated_at ON security_alerts;
CREATE TRIGGER trg_security_alerts_updated_at
BEFORE UPDATE ON security_alerts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_incidents_updated_at ON incidents;
CREATE TRIGGER trg_incidents_updated_at
BEFORE UPDATE ON incidents
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_customer_recommendations_updated_at ON customer_recommendations;
CREATE TRIGGER trg_customer_recommendations_updated_at
BEFORE UPDATE ON customer_recommendations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_monthly_reports_updated_at ON monthly_reports;
CREATE TRIGGER trg_monthly_reports_updated_at
BEFORE UPDATE ON monthly_reports
FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE INDEX IF NOT EXISTS idx_platform_users_tenant_id ON platform_users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_contacts_tenant_id ON tenant_contacts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_activation_tokens_tenant_id ON appliance_activation_tokens(tenant_id);
CREATE INDEX IF NOT EXISTS idx_appliances_tenant_id ON appliances(tenant_id);
CREATE INDEX IF NOT EXISTS idx_appliances_status ON appliances(status);
CREATE INDEX IF NOT EXISTS idx_assets_tenant_id ON protected_assets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_heartbeats_appliance_time ON appliance_heartbeats(appliance_id, heartbeat_at DESC);


CREATE INDEX IF NOT EXISTS idx_alerts_tenant_status ON security_alerts(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON security_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON security_alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_tenant_status ON incidents(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity);
CREATE INDEX IF NOT EXISTS idx_timeline_incident_time ON incident_timeline(incident_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_tenant_status ON notification_events(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_recommendations_tenant_status ON customer_recommendations(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_reports_tenant_month ON monthly_reports(tenant_id, report_month DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);

