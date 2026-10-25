-- Service Catalog list pricing (Admin-editable). Additive; does not replace static catalog copy.
CREATE TABLE IF NOT EXISTS service_catalog_pricing (
    service_key TEXT PRIMARY KEY,
    service_name TEXT NOT NULL,
    pricing_display TEXT NOT NULL,
    pricing_notes TEXT,
    competitor_value TEXT,
    is_core BOOLEAN NOT NULL DEFAULT FALSE,
    requestable BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 100,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by UUID REFERENCES platform_users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_service_catalog_pricing_sort
    ON service_catalog_pricing (sort_order ASC, service_key ASC);

INSERT INTO service_catalog_pricing (
    service_key, service_name, pricing_display, competitor_value, is_core, requestable, sort_order
) VALUES
    ('log_event_monitoring', 'Log & Event Monitoring', 'Included in Silver', 'Competitor value: ~$4.00 / endpoint / month', TRUE, FALSE, 10),
    ('incident_response', 'Incident Response & Casework', 'Included in Silver', 'Competitor value: ~$1,500 / month SOC retainer', TRUE, FALSE, 20),
    ('security_automation', 'Security Automation & Containment', 'Included in Gold', 'Competitor value: ~$2,000 / month SOAR engine', FALSE, TRUE, 30),
    ('vulnerability_management', 'Vulnerability Management (VMaaS)', 'Included in Gold', 'Competitor avg: $6.50–$9.00 / device / month', FALSE, TRUE, 40),
    ('continuous_compliance', 'Continuous Compliance & Hardening (CaaS)', 'Included in Platinum', 'Competitor avg: $5.00–$8.00 / device / month', FALSE, TRUE, 50),
    ('network_detection_response', 'Network Detection & Response (NDR)', 'Included in Platinum', 'Uncapped data ingestion — no per-GB fees', FALSE, TRUE, 60),
    ('threat_intelligence', 'Threat Intelligence & Enrichment', 'Included in Platinum', 'Flat tenant fee', FALSE, TRUE, 70),
    ('endpoint_forensics_deception', 'Endpoint Forensics & Deception Hunting', 'Included in Platinum', 'Per-endpoint advanced response', FALSE, TRUE, 80),
    ('external_attack_surface', 'External Attack Surface Management (EASM)', 'Included in Gold', 'Zero agents required', FALSE, TRUE, 90),
    ('cloud_identity_protection', 'Cloud & Identity Protection (ITDR)', 'Included in Silver', 'Microsoft 365 / Entra ID', FALSE, TRUE, 100)
ON CONFLICT (service_key) DO UPDATE SET
    pricing_display = EXCLUDED.pricing_display,
    competitor_value = EXCLUDED.competitor_value,
    updated_at = NOW();
