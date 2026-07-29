-- KB-086: Expand service upgrade request keys for Services catalog add-ons.

ALTER TABLE service_upgrade_requests
  DROP CONSTRAINT IF EXISTS service_upgrade_requests_service_key_check;

ALTER TABLE service_upgrade_requests
  ADD CONSTRAINT service_upgrade_requests_service_key_check
  CHECK (service_key IN (
    'vulnerability_management',
    'network_traffic_analysis',
    'threat_intelligence',
    'endpoint_forensics',
    'security_automation',
    'other'
  ));
