#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
DB_USER="mssp_admin"
DB_NAME="mssp_control"

cd "$PROJECT_DIR"

echo "============================================================"
echo "KB-007: Seed remaining demo data"
echo "Target: $PROJECT_DIR"
echo "============================================================"

if [ ! -f "docker-compose.yml" ]; then
  echo "ERROR: docker-compose.yml not found in $PROJECT_DIR"
  exit 1
fi

if ! docker compose ps "$DB_SERVICE" >/dev/null 2>&1; then
  echo "ERROR: Docker Compose service '$DB_SERVICE' is not available."
  exit 1
fi

echo "Checking PostgreSQL connectivity..."
docker compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME"

echo "Applying demo alert, incident, timeline, recommendation, notification, and report..."

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM tenants WHERE short_code = 'DEMO') THEN
        RAISE EXCEPTION 'Required tenant DEMO does not exist. Run KB-007 Step 6A foundation seed first.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM tenants t
        JOIN appliances a ON a.tenant_id = t.id
        WHERE t.short_code = 'DEMO'
          AND a.appliance_name = 'demo-appliance-01'
    ) THEN
        RAISE EXCEPTION 'Required appliance demo-appliance-01 does not exist.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM tenants t
        JOIN protected_assets pa ON pa.tenant_id = t.id
        WHERE t.short_code = 'DEMO'
          AND pa.hostname = 'demo-sql-server-01'
    ) THEN
        RAISE EXCEPTION 'Required asset demo-sql-server-01 does not exist.';
    END IF;
END $$;

DELETE FROM notification_events ne
USING tenants t
WHERE ne.tenant_id = t.id
  AND t.short_code = 'DEMO'
  AND ne.recipient_address = '+910000000003';

DELETE FROM customer_recommendations cr
USING tenants t
WHERE cr.tenant_id = t.id
  AND t.short_code = 'DEMO'
  AND cr.title = 'Review suspicious failed login source';

DELETE FROM monthly_reports mr
USING tenants t
WHERE mr.tenant_id = t.id
  AND t.short_code = 'DEMO'
  AND mr.report_month = date_trunc('month', now())::date;

DELETE FROM incident_comments ic
USING incidents i
WHERE ic.incident_id = i.id
  AND i.incident_number = 'INC-DEMO-0001';

DELETE FROM incident_timeline it
USING incidents i
WHERE it.incident_id = i.id
  AND i.incident_number = 'INC-DEMO-0001';

DELETE FROM incident_alerts ia
USING incidents i
WHERE ia.incident_id = i.id
  AND i.incident_number = 'INC-DEMO-0001';

DELETE FROM incidents
WHERE incident_number = 'INC-DEMO-0001';

DELETE FROM security_alerts sa
USING tenants t
WHERE sa.tenant_id = t.id
  AND t.short_code = 'DEMO'
  AND sa.external_alert_id = 'demo-wazuh-001';

WITH inserted_alert AS (
    INSERT INTO security_alerts (
        tenant_id,
        appliance_id,
        asset_id,
        source_tool,
        external_alert_id,
        severity,
        alert_title,
        alert_description,
        event_time,
        source_ip,
        destination_ip,
        source_user,
        destination_host,
        raw_event,
        ai_plain_summary,
        ai_technical_summary,
        ai_likely_attack_type,
        ai_business_impact,
        ai_recommended_action,
        ai_false_positive_score,
        mitre_mapping,
        customer_visible,
        status
    )
    SELECT
        t.id,
        a.id,
        pa.id,
        'wazuh',
        'demo-wazuh-001',
        'high',
        'Multiple failed login attempts detected',
        'Several failed login attempts were detected against a critical SQL Server asset.',
        now(),
        '192.168.10.25',
        '192.168.10.50',
        'unknown-user',
        'demo-sql-server-01',
        '{"rule_id":"5710","event_id":"4625","source":"windows_eventchannel","demo":true}'::jsonb,
        'Multiple failed login attempts were detected against the SQL server. This may indicate password guessing or unauthorized access attempts.',
        'Wazuh reported repeated Windows failed logon events targeting demo-sql-server-01 from 192.168.10.25.',
        'Credential Access / Brute Force Attempt',
        'A successful compromise of this server could impact a critical database workload.',
        'Validate whether the source IP is expected. If not, block the source, review failed login patterns, and confirm MFA/password policy.',
        20.00,
        '{"tactic":"Credential Access","technique":"Brute Force","technique_id":"T1110"}'::jsonb,
        true,
        'incident_created'
    FROM tenants t
    JOIN appliances a ON a.tenant_id = t.id
    JOIN protected_assets pa ON pa.tenant_id = t.id
    WHERE t.short_code = 'DEMO'
      AND a.appliance_name = 'demo-appliance-01'
      AND pa.hostname = 'demo-sql-server-01'
    RETURNING id, tenant_id
),
inserted_incident AS (
    INSERT INTO incidents (
        tenant_id,
        primary_alert_id,
        incident_number,
        title,
        severity,
        status,
        assigned_to_user_id,
        customer_visible_summary,
        business_impact,
        customer_action_required,
        internal_notes
    )
    SELECT
        ia.tenant_id,
        ia.id,
        'INC-DEMO-0001',
        'Possible brute-force attempt against SQL Server',
        'high',
        'open',
        u.id,
        'Multiple failed login attempts were detected against your SQL server. The SOC team is reviewing the activity.',
        'If successful, this type of activity could allow unauthorized access to a critical database server.',
        'Please confirm whether the source IP 192.168.10.25 is expected in your environment.',
        'Demo incident created from demo-wazuh-001 for dashboard validation.'
    FROM inserted_alert ia
    LEFT JOIN platform_users u ON u.email = 'soc.manager@example.local'
    RETURNING id, tenant_id, primary_alert_id
)
INSERT INTO incident_alerts (incident_id, alert_id)
SELECT id, primary_alert_id
FROM inserted_incident;

INSERT INTO incident_timeline (
    incident_id,
    event_type,
    visibility,
    title,
    details,
    created_by_user_id
)
SELECT
    i.id,
    'created',
    'customer',
    'Incident created',
    'SOC created this incident from a high-severity failed-login alert.',
    u.id
FROM incidents i
LEFT JOIN platform_users u ON u.email = 'soc.manager@example.local'
WHERE i.incident_number = 'INC-DEMO-0001';

INSERT INTO incident_timeline (
    incident_id,
    event_type,
    visibility,
    title,
    details,
    created_by_user_id
)
SELECT
    i.id,
    'action_taken',
    'internal',
    'Initial triage started',
    'Analyst reviewing source IP, affected asset, and failed login frequency.',
    u.id
FROM incidents i
LEFT JOIN platform_users u ON u.email = 'soc.manager@example.local'
WHERE i.incident_number = 'INC-DEMO-0001';

INSERT INTO incident_comments (
    incident_id,
    created_by_user_id,
    visibility,
    comment_text
)
SELECT
    i.id,
    u.id,
    'internal',
    'Demo note: validate whether 192.168.10.25 is an approved jump host or unauthorized source.'
FROM incidents i
LEFT JOIN platform_users u ON u.email = 'soc.manager@example.local'
WHERE i.incident_number = 'INC-DEMO-0001';

INSERT INTO customer_recommendations (
    tenant_id,
    related_alert_id,
    related_incident_id,
    title,
    description,
    priority,
    category,
    status,
    customer_visible,
    due_at
)
SELECT
    i.tenant_id,
    i.primary_alert_id,
    i.id,
    'Review suspicious failed login source',
    'Confirm whether 192.168.10.25 is an authorized system. If it is not expected, block it and review password/MFA policy for the affected SQL server.',
    'high',
    'identity-and-access',
    'open',
    true,
    now() + interval '7 days'
FROM incidents i
WHERE i.incident_number = 'INC-DEMO-0001';

INSERT INTO notification_events (
    tenant_id,
    incident_id,
    alert_id,
    notification_type,
    recipient_name,
    recipient_address,
    message_body,
    provider,
    provider_message_id,
    status,
    sent_at,
    delivered_at
)
SELECT
    i.tenant_id,
    i.id,
    i.primary_alert_id,
    'whatsapp',
    'Demo Security Contact',
    '+910000000003',
    'MSSP Alert INC-DEMO-0001: High-severity failed login activity detected against demo-sql-server-01. SOC review is in progress. Please confirm whether source IP 192.168.10.25 is expected.',
    'demo-provider',
    'demo-message-id-0001',
    'delivered',
    now(),
    now()
FROM incidents i
WHERE i.incident_number = 'INC-DEMO-0001';

INSERT INTO monthly_reports (
    tenant_id,
    report_month,
    status,
    executive_summary,
    metrics,
    published_at
)
SELECT
    t.id,
    date_trunc('month', now())::date,
    'draft',
    'Demo monthly report placeholder. One high-severity security incident was identified for dashboard validation.',
    '{"open_incidents":1,"high_alerts":1,"online_appliances":1,"protected_assets":1,"open_recommendations":1}'::jsonb,
    NULL
FROM tenants t
WHERE t.short_code = 'DEMO';

INSERT INTO audit_logs (
    tenant_id,
    actor_user_id,
    action,
    entity_type,
    entity_id,
    source_ip,
    details
)
SELECT
    i.tenant_id,
    u.id,
    'seed_demo_data',
    'incident',
    i.id,
    '192.168.0.201',
    '{"script":"kb007_seed_remaining_demo_data.sh","incident_number":"INC-DEMO-0001"}'::jsonb
FROM incidents i
LEFT JOIN platform_users u ON u.email = 'soc.manager@example.local'
WHERE i.incident_number = 'INC-DEMO-0001';

COMMIT;

SELECT
    'remaining_demo_seed_completed' AS result,
    (SELECT count(*) FROM security_alerts WHERE external_alert_id = 'demo-wazuh-001') AS alerts,
    (SELECT count(*) FROM incidents WHERE incident_number = 'INC-DEMO-0001') AS incidents,
    (SELECT count(*) FROM incident_timeline it JOIN incidents i ON i.id = it.incident_id WHERE i.incident_number = 'INC-DEMO-0001') AS timeline_entries,
    (SELECT count(*) FROM customer_recommendations cr JOIN tenants t ON t.id = cr.tenant_id WHERE t.short_code = 'DEMO') AS recommendations,
    (SELECT count(*) FROM notification_events ne JOIN tenants t ON t.id = ne.tenant_id WHERE t.short_code = 'DEMO') AS notifications,
    (SELECT count(*) FROM monthly_reports mr JOIN tenants t ON t.id = mr.tenant_id WHERE t.short_code = 'DEMO') AS reports;
SQL

echo "============================================================"
echo "KB-007 demo remaining seed completed."
echo "============================================================"
