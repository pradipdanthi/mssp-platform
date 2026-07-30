#!/usr/bin/env bash
# KB-091: Delete Alpha-Win 92213 noise incidents; keep Test1 + reference tickers.
# Keeps:
#   TH-0001 — Test 1 encoded PowerShell detect
#   TH-0002 — Test 1 companion 92213 (same session, 2026-07-29)
#   TH-0003 — today's remedi Temp script-drop reference (if present)
#   Plus: newest single 92213 "file dropped..." incident if not already kept
set -euo pipefail
cd /opt/mssp-control

docker exec -i mssp-postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
BEGIN;

CREATE TEMP TABLE keep_incidents AS
SELECT i.id AS incident_id
FROM incidents i
JOIN tenants t ON t.id = i.tenant_id
WHERE t.short_code = 'ALPHAWINCORP-6VS2'
  AND i.incident_number IN (
    'INC-ALPHAWINCORP-6VS2-TH-0001',
    'INC-ALPHAWINCORP-6VS2-TH-0002',
    'INC-ALPHAWINCORP-6VS2-TH-0003'
  );

-- If TH-0003 missing, also keep newest 92213 file-drop incident as reference
INSERT INTO keep_incidents (incident_id)
SELECT i.id
FROM incidents i
JOIN tenants t ON t.id = i.tenant_id
WHERE t.short_code = 'ALPHAWINCORP-6VS2'
  AND i.title ILIKE 'Executable file dropped in folder commonly used by malware%'
  AND NOT EXISTS (SELECT 1 FROM keep_incidents k WHERE k.incident_id = i.id)
ORDER BY i.opened_at DESC
LIMIT 1;

CREATE TEMP TABLE doomed AS
SELECT i.id AS incident_id, i.primary_alert_id
FROM incidents i
JOIN tenants t ON t.id = i.tenant_id
WHERE t.short_code = 'ALPHAWINCORP-6VS2'
  AND NOT EXISTS (SELECT 1 FROM keep_incidents k WHERE k.incident_id = i.id);

CREATE TEMP TABLE doomed_alerts AS
SELECT DISTINCT alert_id FROM (
  SELECT ia.alert_id
  FROM incident_alerts ia
  JOIN doomed d ON d.incident_id = ia.incident_id
  UNION
  SELECT primary_alert_id AS alert_id
  FROM doomed
  WHERE primary_alert_id IS NOT NULL
) x;

SELECT
  (SELECT COUNT(*) FROM keep_incidents) AS incidents_kept,
  (SELECT COUNT(*) FROM doomed) AS incidents_to_delete,
  (SELECT COUNT(*) FROM doomed_alerts) AS linked_alerts_to_delete;

DELETE FROM incident_timeline WHERE incident_id IN (SELECT incident_id FROM doomed);
DELETE FROM incident_alerts WHERE incident_id IN (SELECT incident_id FROM doomed);

UPDATE incidents SET primary_alert_id = NULL
WHERE id IN (SELECT incident_id FROM doomed);

DELETE FROM security_alerts WHERE id IN (SELECT alert_id FROM doomed_alerts);
DELETE FROM incidents WHERE id IN (SELECT incident_id FROM doomed);

DELETE FROM security_alerts sa
WHERE sa.tenant_id = (SELECT id FROM tenants WHERE short_code='ALPHAWINCORP-6VS2')
  AND NOT EXISTS (
    SELECT 1 FROM incidents i
    WHERE i.tenant_id = sa.tenant_id AND i.primary_alert_id = sa.id
  )
  AND NOT EXISTS (
    SELECT 1 FROM incident_alerts ia
    JOIN incidents i ON i.id = ia.incident_id
    WHERE i.tenant_id = sa.tenant_id AND ia.alert_id = sa.id
  );

SELECT incident_number, status, opened_at::date AS opened, left(title,50) AS title
FROM incidents
WHERE tenant_id = (SELECT id FROM tenants WHERE short_code='ALPHAWINCORP-6VS2')
ORDER BY incident_number;

SELECT COUNT(*) AS alerts_left FROM security_alerts
WHERE tenant_id = (SELECT id FROM tenants WHERE short_code='ALPHAWINCORP-6VS2');

COMMIT;
SQL

echo "CLEANUP DONE: kept Test1 + 92213 reference ticker(s)"
