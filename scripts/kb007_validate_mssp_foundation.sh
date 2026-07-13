#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
DB_SERVICE="postgres"
DB_USER="mssp_admin"
DB_NAME="mssp_control"

cd "$PROJECT_DIR"

echo "============================================================"
echo "KB-007: Validate MSSP foundation"
echo "Target: $PROJECT_DIR"
echo "============================================================"

if [ ! -f "docker-compose.yml" ]; then
  echo "ERROR: docker-compose.yml not found in $PROJECT_DIR"
  exit 1
fi

echo
echo "----- Docker services -----"
docker compose ps

echo
echo "----- PostgreSQL readiness -----"
docker compose exec -T "$DB_SERVICE" pg_isready -U "$DB_USER" -d "$DB_NAME"

echo
echo "----- Schema counts -----"
docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" <<'SQL'
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

echo
echo "----- Demo foundation counts -----"
docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" <<'SQL'
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
SELECT 'incident_timeline', count(*) FROM incident_timeline it JOIN incidents i ON i.id = it.incident_id WHERE i.incident_number = 'INC-DEMO-0001'
UNION ALL
SELECT 'customer_recommendations', count(*) FROM customer_recommendations cr JOIN tenants t ON t.id = cr.tenant_id WHERE t.short_code = 'DEMO'
UNION ALL
SELECT 'notification_events', count(*) FROM notification_events ne JOIN tenants t ON t.id = ne.tenant_id WHERE t.short_code = 'DEMO'
UNION ALL
SELECT 'monthly_reports', count(*) FROM monthly_reports mr JOIN tenants t ON t.id = mr.tenant_id WHERE t.short_code = 'DEMO'
ORDER BY item;
SQL

echo
echo "----- Admin dashboard preview -----"
docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" <<'SQL'
SELECT
    t.name AS tenant,
    COUNT(DISTINCT a.id) AS appliances,
    COUNT(DISTINCT CASE WHEN a.status = 'online' THEN a.id END) AS online_appliances,
    COUNT(DISTINCT sa.id) AS alerts,
    COUNT(DISTINCT CASE WHEN sa.severity IN ('high','critical') THEN sa.id END) AS high_or_critical_alerts,
    COUNT(DISTINCT i.id) AS incidents,
    COUNT(DISTINCT CASE WHEN i.status IN ('open','in_progress','waiting_customer') THEN i.id END) AS open_incidents
FROM tenants t
LEFT JOIN appliances a ON a.tenant_id = t.id
LEFT JOIN security_alerts sa ON sa.tenant_id = t.id
LEFT JOIN incidents i ON i.tenant_id = t.id
WHERE t.short_code = 'DEMO'
GROUP BY t.name;
SQL

echo
echo "----- Customer dashboard preview -----"
docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" <<'SQL'
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

echo
echo "----- Validation verdict -----"
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
DO $$
DECLARE
    table_count int;
    trigger_count int;
    demo_tenant_count int;
    demo_alert_count int;
    demo_incident_count int;
BEGIN
    SELECT count(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema='public' AND table_type='BASE TABLE';

    SELECT count(*) INTO trigger_count
    FROM information_schema.triggers
    WHERE trigger_schema='public';

    SELECT count(*) INTO demo_tenant_count
    FROM tenants
    WHERE short_code='DEMO';

    SELECT count(*) INTO demo_alert_count
    FROM security_alerts
    WHERE external_alert_id='demo-wazuh-001';

    SELECT count(*) INTO demo_incident_count
    FROM incidents
    WHERE incident_number='INC-DEMO-0001';

    IF table_count <> 16 THEN
        RAISE EXCEPTION 'Expected 16 tables, found %', table_count;
    END IF;

    IF trigger_count <> 9 THEN
        RAISE EXCEPTION 'Expected 9 triggers, found %', trigger_count;
    END IF;

    IF demo_tenant_count <> 1 THEN
        RAISE EXCEPTION 'Expected 1 DEMO tenant, found %', demo_tenant_count;
    END IF;

    IF demo_alert_count <> 1 THEN
        RAISE EXCEPTION 'Expected 1 demo alert, found %', demo_alert_count;
    END IF;

    IF demo_incident_count <> 1 THEN
        RAISE EXCEPTION 'Expected 1 demo incident, found %', demo_incident_count;
    END IF;
END $$;

SELECT 'VALIDATION PASSED' AS result;
SQL

echo
echo "============================================================"
echo "KB-007 validation completed successfully."
echo "============================================================"
