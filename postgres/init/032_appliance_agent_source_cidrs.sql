-- Appliance agent-source CIDRs (multi-subnet ingest allow-list).
-- Additive only — never drops existing objects.

ALTER TABLE appliances
  ADD COLUMN IF NOT EXISTS agent_source_cidrs TEXT[] NOT NULL DEFAULT '{}'::text[];

COMMENT ON COLUMN appliances.agent_source_cidrs IS
  'IPv4 CIDRs allowed to reach local Wazuh Manager ports 1514/1515; pushed to appliance via set_agent_cidrs job';
