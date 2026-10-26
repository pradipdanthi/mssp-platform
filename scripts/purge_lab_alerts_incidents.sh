#!/usr/bin/env bash
# Purge ALL security_alerts + incidents (and related join/timeline/comment rows).
# Uses Postgres container env — does not source host .env (avoids parse errors).
set -euo pipefail

echo "Counting before purge…"
docker exec mssp-postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT '\''alerts'\'' AS t, count(*) FROM security_alerts
UNION ALL SELECT '\''incidents'\'', count(*) FROM incidents;"'

docker exec -i mssp-postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<'SQL'
BEGIN;
UPDATE notification_events SET alert_id = NULL WHERE alert_id IS NOT NULL;
UPDATE notification_events SET incident_id = NULL WHERE incident_id IS NOT NULL;
UPDATE customer_recommendations SET related_alert_id = NULL WHERE related_alert_id IS NOT NULL;
UPDATE customer_recommendations SET related_incident_id = NULL WHERE related_incident_id IS NOT NULL;
UPDATE edr_action_executions SET alert_id = NULL WHERE alert_id IS NOT NULL;
UPDATE edr_action_executions SET incident_id = NULL WHERE incident_id IS NOT NULL;
UPDATE incidents SET primary_alert_id = NULL WHERE primary_alert_id IS NOT NULL;
DELETE FROM alert_ai_triage_cache;
DELETE FROM edr_process_events;
DELETE FROM incident_comments;
DELETE FROM incident_timeline;
DELETE FROM incident_alerts;
DELETE FROM incidents;
DELETE FROM security_alerts;
COMMIT;
SELECT 'alerts' AS t, count(*) FROM security_alerts
UNION ALL SELECT 'incidents', count(*) FROM incidents;
SQL

echo "OK: alerts and incidents purged."
