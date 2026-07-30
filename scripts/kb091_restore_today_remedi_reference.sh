#!/usr/bin/env bash
# KB-091: Restore today's AR remedi Temp script-drop reference (TH-0003).
# TH-0001 = Test 1 detect. TH-0002 = Test 1 companion 92213 (same night).
# TH-0003 = today's remedi install burst reference (2026-07-30).
set -euo pipefail
cd /opt/mssp-control

docker exec -i mssp-postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
BEGIN;

-- TH-0002 alert should reflect linked incident (not false_positive)
UPDATE security_alerts
SET status = 'incident_created', updated_at = now()
WHERE id = '0a4b37aa-688b-4a45-9301-ef024dacd4d8'
  AND status = 'false_positive';

UPDATE incidents
SET internal_notes = trim(both E'\n' from (
  'Test 1 companion (2026-07-29): rule 92213 file-drop from same encoded-PowerShell session. '
  || 'AR remedi reference is TH-0003 (2026-07-30).'
))
WHERE incident_number = 'INC-ALPHAWINCORP-6VS2-TH-0002';

-- Skip if reference already restored
DO $$
DECLARE
  v_tenant_id UUID;
  v_alert_id UUID;
  v_incident_id UUID;
BEGIN
  SELECT id INTO v_tenant_id FROM tenants WHERE short_code = 'ALPHAWINCORP-6VS2';
  IF v_tenant_id IS NULL THEN
    RAISE EXCEPTION 'tenant ALPHAWINCORP-6VS2 not found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM incidents
    WHERE tenant_id = v_tenant_id
      AND incident_number = 'INC-ALPHAWINCORP-6VS2-TH-0003'
  ) THEN
    RAISE NOTICE 'TH-0003 already exists — skipping insert';
    RETURN;
  END IF;

  INSERT INTO security_alerts (
    tenant_id, source_tool, external_alert_id,
    severity, alert_title, alert_description,
    event_time, destination_host,
    customer_visible, status, ai_plain_summary
  ) VALUES (
    v_tenant_id, 'wazuh', '1785391477.4392428',
    'critical',
    'Executable file dropped in folder commonly used by malware',
    'Representative Wazuh 92213 from 2026-07-30 AR remedi install burst. '
      || 'Sysmon FileCreate on Temp policy-test script (__PSScriptPolicyTest_*.ps1) '
      || 'during elevated PowerShell on WIN-BL72S84GDTF. '
      || '38 duplicate incidents deleted; this row is the kept reference ticker.',
    '2026-07-30 11:34:44+05:30', 'WIN-BL72S84GDTF',
    false, 'incident_created',
    'Reference: AR remedi install caused expected 92213 Temp script-drop noise.'
  )
  RETURNING id INTO v_alert_id;

  INSERT INTO incidents (
    tenant_id, primary_alert_id, incident_number, title,
    severity, status, customer_visible_summary, business_impact,
    internal_notes, opened_at, closed_at
  ) VALUES (
    v_tenant_id, v_alert_id, 'INC-ALPHAWINCORP-6VS2-TH-0003',
    'Executable file dropped in folder commonly used by malware',
    'critical', 'closed',
    'Reference incident — controlled AR remedi activity on the endpoint.',
    'No customer impact. SOC reference for rule 92213 Temp file-drop during remedi install.',
    '[KB-091] Reference ticker for 2026-07-30 remedi burst (38 duplicates deleted). '
      || 'Pattern: __PSScriptPolicyTest_* in AppData\\Local\\Temp during elevated PowerShell. '
      || 'Phase-1 now suppresses new incidents for this noise; correlate same-title bursts.',
    '2026-07-30 11:34:44+05:30', now()
  )
  RETURNING id INTO v_incident_id;

  INSERT INTO incident_alerts (incident_id, alert_id)
  VALUES (v_incident_id, v_alert_id);

  INSERT INTO incident_timeline (
    incident_id, event_type, visibility, title, details
  ) VALUES (
    v_incident_id, 'comment', 'internal',
    'Reference incident restored after burst cleanup',
  'KB-091: representative alert from remedi install flood; closed for SOC reference only.'
  );
END $$;

SELECT incident_number, status, opened_at::date AS opened, left(title,45) AS title
FROM incidents
WHERE tenant_id = (SELECT id FROM tenants WHERE short_code='ALPHAWINCORP-6VS2')
ORDER BY incident_number;

SELECT status, created_at::date AS created, external_alert_id, left(alert_title,45) AS title
FROM security_alerts
WHERE tenant_id = (SELECT id FROM tenants WHERE short_code='ALPHAWINCORP-6VS2')
ORDER BY created_at;

COMMIT;
SQL

echo "REFERENCE RESTORED: TH-0003 = today's remedi Temp script-drop reference"
