#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
REDIS_SERVICE="redis"
DB_USER="mssp_admin"
DB_NAME="mssp_control"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-007 FULL VALIDATION: MSSP Control Plane Foundation"
echo "Mode: READ-ONLY validation. This script does not delete or modify data."
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1"
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

section "1. Project file validation"

[ -d "$PROJECT_DIR" ] || fail "Project directory missing: $PROJECT_DIR"
[ -f "$PROJECT_DIR/docker-compose.yml" ] || fail "docker-compose.yml missing"
[ -f "$PROJECT_DIR/.env" ] || fail ".env file missing"
[ -d "$PROJECT_DIR/postgres/init" ] || fail "postgres/init directory missing"
[ -f "$PROJECT_DIR/postgres/init/001_mssp_core_schema.sql" ] || fail "Core schema file missing"
[ -d "$PROJECT_DIR/scripts" ] || fail "scripts directory missing"

echo "Project directory exists: $PROJECT_DIR"
echo "docker-compose.yml exists"
echo ".env exists"
echo "postgres/init/001_mssp_core_schema.sql exists"
echo "scripts directory exists"

echo
echo "Core schema file summary:"
ls -lh "$PROJECT_DIR/postgres/init/001_mssp_core_schema.sql"
echo "CREATE TABLE statements:  $(grep -c 'CREATE TABLE' "$PROJECT_DIR/postgres/init/001_mssp_core_schema.sql" || true)"
echo "CREATE TRIGGER statements: $(grep -c 'CREATE TRIGGER' "$PROJECT_DIR/postgres/init/001_mssp_core_schema.sql" || true)"
echo "CREATE INDEX statements:   $(grep -c 'CREATE INDEX' "$PROJECT_DIR/postgres/init/001_mssp_core_schema.sql" || true)"

section "2. Docker Compose validation"

docker compose config >/tmp/kb007_compose_config_check.txt
echo "Docker Compose file syntax: OK"

echo
echo "Docker services:"
docker compose ps

postgres_status="$(docker inspect -f '{{.State.Health.Status}}' mssp-postgres 2>/dev/null || echo 'missing')"
redis_status="$(docker inspect -f '{{.State.Health.Status}}' mssp-redis 2>/dev/null || echo 'missing')"

echo
echo "mssp-postgres health: $postgres_status"
echo "mssp-redis health:    $redis_status"

[ "$postgres_status" = "healthy" ] || fail "mssp-postgres is not healthy"
[ "$redis_status" = "healthy" ] || fail "mssp-redis is not healthy"

section "3. PostgreSQL and Redis readiness"

docker compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME"
redis_password="$(grep '^REDIS_PASSWORD=' "$PROJECT_DIR/.env" | cut -d= -f2-)"
docker compose exec -T "$REDIS_SERVICE" redis-cli --no-auth-warning -a "$redis_password" ping | grep -q "PONG"
echo "Redis ping: PONG"

section "4. Database schema object counts"

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
SELECT 'tables' AS item, count(*) AS count
FROM information_schema.tables
WHERE table_schema='public' AND table_type='BASE TABLE'
UNION ALL
SELECT 'triggers', count(*)
FROM information_schema.triggers
WHERE trigger_schema='public'
UNION ALL
SELECT 'indexes', count(*)
FROM pg_indexes
WHERE schemaname='public'
ORDER BY item;
SQL

section "5. Expected table existence check"

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
WITH expected(table_name) AS (
    VALUES
    ('tenants'),
    ('platform_users'),
    ('tenant_contacts'),
    ('appliance_activation_tokens'),
    ('appliances'),
    ('protected_assets'),
    ('appliance_heartbeats'),
    ('security_alerts'),
    ('incidents'),
    ('incident_alerts'),
    ('incident_timeline'),
    ('incident_comments'),
    ('notification_events'),
    ('customer_recommendations'),
    ('monthly_reports'),
    ('audit_logs')
),
actual AS (
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema='public'
      AND table_type='BASE TABLE'
)
SELECT
    e.table_name,
    CASE WHEN a.table_name IS NULL THEN 'MISSING' ELSE 'OK' END AS status
FROM expected e
LEFT JOIN actual a ON a.table_name = e.table_name
ORDER BY e.table_name;
SQL

section "6. Expected trigger existence check"

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
WITH expected(trigger_name) AS (
    VALUES
    ('trg_tenants_updated_at'),
    ('trg_platform_users_updated_at'),
    ('trg_tenant_contacts_updated_at'),
    ('trg_appliances_updated_at'),
    ('trg_protected_assets_updated_at'),
    ('trg_security_alerts_updated_at'),
    ('trg_incidents_updated_at'),
    ('trg_customer_recommendations_updated_at'),
    ('trg_monthly_reports_updated_at')
),
actual AS (
    SELECT trigger_name
    FROM information_schema.triggers
    WHERE trigger_schema='public'
)
SELECT
    e.trigger_name,
    CASE WHEN a.trigger_name IS NULL THEN 'MISSING' ELSE 'OK' END AS status
FROM expected e
LEFT JOIN actual a ON a.trigger_name = e.trigger_name
ORDER BY e.trigger_name;
SQL

section "7. Expected custom index existence check"

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
WITH expected(indexname) AS (
    VALUES
    ('idx_platform_users_tenant_id'),
    ('idx_tenant_contacts_tenant_id'),
    ('idx_activation_tokens_tenant_id'),
    ('idx_appliances_tenant_id'),
    ('idx_appliances_status'),
    ('idx_assets_tenant_id'),
    ('idx_heartbeats_appliance_time'),
    ('idx_alerts_tenant_status'),
    ('idx_alerts_severity'),
    ('idx_alerts_created_at'),
    ('idx_incidents_tenant_status'),
    ('idx_incidents_severity'),
    ('idx_timeline_incident_time'),
    ('idx_notifications_tenant_status'),
    ('idx_recommendations_tenant_status'),
    ('idx_reports_tenant_month'),
    ('idx_audit_logs_created_at')
),
actual AS (
    SELECT indexname
    FROM pg_indexes
    WHERE schemaname='public'
)
SELECT
    e.indexname,
    CASE WHEN a.indexname IS NULL THEN 'MISSING' ELSE 'OK' END AS status
FROM expected e
LEFT JOIN actual a ON a.indexname = e.indexname
ORDER BY e.indexname;
SQL

section "8. Demo data existence counts"

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
SELECT 'tenants' AS item, count(*) AS count FROM tenants WHERE short_code = 'DEMO'
UNION ALL
SELECT 'platform_users', count(*) FROM platform_users WHERE email IN ('soc.manager@example.local', 'customer.admin@example.local')
UNION ALL
SELECT 'tenant_contacts', count(*) FROM tenant_contacts c JOIN tenants t ON t.id = c.tenant_id WHERE t.short_code = 'DEMO'
UNION ALL
SELECT 'activation_tokens', count(*) FROM appliance_activation_tokens tok JOIN tenants t ON t.id = tok.tenant_id WHERE t.short_code = 'DEMO'
UNION ALL
SELECT 'appliances', count(*) FROM appliances a JOIN tenants t ON t.id = a.tenant_id WHERE t.short_code = 'DEMO'
UNION ALL
SELECT 'protected_assets', count(*) FROM protected_assets pa JOIN tenants t ON t.id = pa.tenant_id WHERE t.short_code = 'DEMO'
UNION ALL
SELECT 'appliance_heartbeats', count(*) FROM appliance_heartbeats h JOIN appliances a ON a.id = h.appliance_id JOIN tenants t ON t.id = a.tenant_id WHERE t.short_code = 'DEMO'
UNION ALL
SELECT 'security_alerts', count(*) FROM security_alerts sa JOIN tenants t ON t.id = sa.tenant_id WHERE t.short_code = 'DEMO'
UNION ALL
SELECT 'incidents', count(*) FROM incidents i JOIN tenants t ON t.id = i.tenant_id WHERE t.short_code = 'DEMO'
UNION ALL
SELECT 'incident_alerts', count(*) FROM incident_alerts ia JOIN incidents i ON i.id = ia.incident_id WHERE i.incident_number = 'INC-DEMO-0001'
UNION ALL
SELECT 'incident_timeline', count(*) FROM incident_timeline it JOIN incidents i ON i.id = it.incident_id WHERE i.incident_number = 'INC-DEMO-0001'
UNION ALL
SELECT 'incident_comments', count(*) FROM incident_comments ic JOIN incidents i ON i.id = ic.incident_id WHERE i.incident_number = 'INC-DEMO-0001'
UNION ALL
SELECT 'customer_recommendations', count(*) FROM customer_recommendations cr JOIN tenants t ON t.id = cr.tenant_id WHERE t.short_code = 'DEMO'
UNION ALL
SELECT 'notification_events', count(*) FROM notification_events ne JOIN tenants t ON t.id = ne.tenant_id WHERE t.short_code = 'DEMO'
UNION ALL
SELECT 'monthly_reports', count(*) FROM monthly_reports mr JOIN tenants t ON t.id = mr.tenant_id WHERE t.short_code = 'DEMO'
UNION ALL
SELECT 'audit_logs', count(*) FROM audit_logs al JOIN tenants t ON t.id = al.tenant_id WHERE t.short_code = 'DEMO'
ORDER BY item;
SQL

section "9. Admin dashboard preview data"

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
SELECT
    t.name AS tenant,
    t.status AS tenant_status,
    t.sla_level,
    t.business_criticality,
    COUNT(DISTINCT a.id) AS appliances,
    COUNT(DISTINCT CASE WHEN a.status = 'online' THEN a.id END) AS online_appliances,
    COUNT(DISTINCT pa.id) AS protected_assets,
    COUNT(DISTINCT sa.id) AS alerts,
    COUNT(DISTINCT CASE WHEN sa.severity IN ('high','critical') THEN sa.id END) AS high_or_critical_alerts,
    COUNT(DISTINCT i.id) AS incidents,
    COUNT(DISTINCT CASE WHEN i.status IN ('open','in_progress','waiting_customer') THEN i.id END) AS open_incidents,
    COUNT(DISTINCT cr.id) AS recommendations,
    COUNT(DISTINCT ne.id) AS notifications
FROM tenants t
LEFT JOIN appliances a ON a.tenant_id = t.id
LEFT JOIN protected_assets pa ON pa.tenant_id = t.id
LEFT JOIN security_alerts sa ON sa.tenant_id = t.id
LEFT JOIN incidents i ON i.tenant_id = t.id
LEFT JOIN customer_recommendations cr ON cr.tenant_id = t.id
LEFT JOIN notification_events ne ON ne.tenant_id = t.id
WHERE t.short_code = 'DEMO'
GROUP BY t.name, t.status, t.sla_level, t.business_criticality;
SQL

section "10. Customer dashboard preview data"

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
SELECT
    i.incident_number,
    i.severity,
    i.status,
    i.customer_visible_summary,
    i.customer_action_required
FROM incidents i
JOIN tenants t ON t.id = i.tenant_id
WHERE t.short_code = 'DEMO'
ORDER BY i.created_at DESC;
SQL

section "11. Appliance health preview"

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
SELECT
    t.name AS tenant,
    a.appliance_name,
    a.site_name,
    a.status,
    a.agent_version,
    a.update_status,
    a.last_seen_at,
    h.health_status,
    h.cpu_percent,
    h.memory_percent,
    h.disk_percent,
    h.heartbeat_at
FROM tenants t
JOIN appliances a ON a.tenant_id = t.id
LEFT JOIN LATERAL (
    SELECT *
    FROM appliance_heartbeats h
    WHERE h.appliance_id = a.id
    ORDER BY h.heartbeat_at DESC
    LIMIT 1
) h ON true
WHERE t.short_code = 'DEMO';
SQL

section "12. Final strict validation verdict"

docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
DO $$
DECLARE
    table_count int;
    trigger_count int;
    custom_index_count int;
    demo_tenant_count int;
    demo_user_count int;
    demo_contact_count int;
    demo_token_count int;
    demo_appliance_count int;
    demo_asset_count int;
    demo_heartbeat_count int;
    demo_alert_count int;
    demo_incident_count int;
    demo_incident_alert_count int;
    demo_timeline_count int;
    demo_comment_count int;
    demo_recommendation_count int;
    demo_notification_count int;
    demo_report_count int;
    demo_audit_count int;
BEGIN
    SELECT count(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema='public' AND table_type='BASE TABLE';

    SELECT count(*) INTO trigger_count
    FROM information_schema.triggers
    WHERE trigger_schema='public';

    WITH expected(indexname) AS (
        VALUES
        ('idx_platform_users_tenant_id'),
        ('idx_tenant_contacts_tenant_id'),
        ('idx_activation_tokens_tenant_id'),
        ('idx_appliances_tenant_id'),
        ('idx_appliances_status'),
        ('idx_assets_tenant_id'),
        ('idx_heartbeats_appliance_time'),
        ('idx_alerts_tenant_status'),
        ('idx_alerts_severity'),
        ('idx_alerts_created_at'),
        ('idx_incidents_tenant_status'),
        ('idx_incidents_severity'),
        ('idx_timeline_incident_time'),
        ('idx_notifications_tenant_status'),
        ('idx_recommendations_tenant_status'),
        ('idx_reports_tenant_month'),
        ('idx_audit_logs_created_at')
    )
    SELECT count(*) INTO custom_index_count
    FROM expected e
    JOIN pg_indexes i ON i.schemaname='public' AND i.indexname=e.indexname;

    SELECT count(*) INTO demo_tenant_count FROM tenants WHERE short_code='DEMO';
    SELECT count(*) INTO demo_user_count FROM platform_users WHERE email IN ('soc.manager@example.local', 'customer.admin@example.local');
    SELECT count(*) INTO demo_contact_count FROM tenant_contacts c JOIN tenants t ON t.id = c.tenant_id WHERE t.short_code='DEMO';
    SELECT count(*) INTO demo_token_count FROM appliance_activation_tokens tok JOIN tenants t ON t.id = tok.tenant_id WHERE t.short_code='DEMO';
    SELECT count(*) INTO demo_appliance_count FROM appliances a JOIN tenants t ON t.id = a.tenant_id WHERE t.short_code='DEMO' AND a.appliance_name='demo-appliance-01';
    SELECT count(*) INTO demo_asset_count FROM protected_assets pa JOIN tenants t ON t.id = pa.tenant_id WHERE t.short_code='DEMO' AND pa.hostname='demo-sql-server-01';
    SELECT count(*) INTO demo_heartbeat_count FROM appliance_heartbeats h JOIN appliances a ON a.id = h.appliance_id JOIN tenants t ON t.id = a.tenant_id WHERE t.short_code='DEMO' AND a.appliance_name='demo-appliance-01';
    SELECT count(*) INTO demo_alert_count FROM security_alerts WHERE external_alert_id='demo-wazuh-001';
    SELECT count(*) INTO demo_incident_count FROM incidents WHERE incident_number='INC-DEMO-0001';
    SELECT count(*) INTO demo_incident_alert_count FROM incident_alerts ia JOIN incidents i ON i.id = ia.incident_id WHERE i.incident_number='INC-DEMO-0001';
    SELECT count(*) INTO demo_timeline_count FROM incident_timeline it JOIN incidents i ON i.id = it.incident_id WHERE i.incident_number='INC-DEMO-0001';
    SELECT count(*) INTO demo_comment_count FROM incident_comments ic JOIN incidents i ON i.id = ic.incident_id WHERE i.incident_number='INC-DEMO-0001';
    SELECT count(*) INTO demo_recommendation_count FROM customer_recommendations cr JOIN tenants t ON t.id = cr.tenant_id WHERE t.short_code='DEMO';
    SELECT count(*) INTO demo_notification_count FROM notification_events ne JOIN tenants t ON t.id = ne.tenant_id WHERE t.short_code='DEMO';
    SELECT count(*) INTO demo_report_count FROM monthly_reports mr JOIN tenants t ON t.id = mr.tenant_id WHERE t.short_code='DEMO';
    SELECT count(*) INTO demo_audit_count FROM audit_logs al JOIN tenants t ON t.id = al.tenant_id WHERE t.short_code='DEMO';

    IF table_count <> 16 THEN RAISE EXCEPTION 'Expected 16 tables, found %', table_count; END IF;
    IF trigger_count <> 9 THEN RAISE EXCEPTION 'Expected 9 triggers, found %', trigger_count; END IF;
    IF custom_index_count <> 17 THEN RAISE EXCEPTION 'Expected 17 custom indexes, found %', custom_index_count; END IF;
    IF demo_tenant_count <> 1 THEN RAISE EXCEPTION 'Expected 1 DEMO tenant, found %', demo_tenant_count; END IF;
    IF demo_user_count <> 2 THEN RAISE EXCEPTION 'Expected 2 demo platform users, found %', demo_user_count; END IF;
    IF demo_contact_count < 1 THEN RAISE EXCEPTION 'Expected at least 1 demo tenant contact, found %', demo_contact_count; END IF;
    IF demo_token_count < 1 THEN RAISE EXCEPTION 'Expected at least 1 demo activation token, found %', demo_token_count; END IF;
    IF demo_appliance_count <> 1 THEN RAISE EXCEPTION 'Expected 1 demo appliance, found %', demo_appliance_count; END IF;
    IF demo_asset_count <> 1 THEN RAISE EXCEPTION 'Expected 1 demo asset, found %', demo_asset_count; END IF;
    IF demo_heartbeat_count < 1 THEN RAISE EXCEPTION 'Expected at least 1 demo heartbeat, found %', demo_heartbeat_count; END IF;
    IF demo_alert_count <> 1 THEN RAISE EXCEPTION 'Expected 1 demo alert, found %', demo_alert_count; END IF;
    IF demo_incident_count <> 1 THEN RAISE EXCEPTION 'Expected 1 demo incident, found %', demo_incident_count; END IF;
    IF demo_incident_alert_count <> 1 THEN RAISE EXCEPTION 'Expected 1 demo incident-alert link, found %', demo_incident_alert_count; END IF;
    IF demo_timeline_count <> 2 THEN RAISE EXCEPTION 'Expected 2 demo timeline entries, found %', demo_timeline_count; END IF;
    IF demo_comment_count <> 1 THEN RAISE EXCEPTION 'Expected 1 demo incident comment, found %', demo_comment_count; END IF;
    IF demo_recommendation_count <> 1 THEN RAISE EXCEPTION 'Expected 1 demo recommendation, found %', demo_recommendation_count; END IF;
    IF demo_notification_count <> 1 THEN RAISE EXCEPTION 'Expected 1 demo notification, found %', demo_notification_count; END IF;
    IF demo_report_count <> 1 THEN RAISE EXCEPTION 'Expected 1 demo monthly report, found %', demo_report_count; END IF;
    IF demo_audit_count < 1 THEN RAISE EXCEPTION 'Expected at least 1 demo audit log, found %', demo_audit_count; END IF;
END $$;

SELECT 'FULL VALIDATION PASSED - MSSP FOUNDATION IS COMPLETE' AS result;
SQL

echo
echo "======================================================================"
echo "KB-007 FULL VALIDATION COMPLETED SUCCESSFULLY"
echo "No destructive actions were performed by this validation script."
echo "======================================================================"
