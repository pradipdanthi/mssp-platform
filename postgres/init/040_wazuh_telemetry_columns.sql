-- KB-110: Persist maximum Wazuh/Sysmon endpoint telemetry on security_alerts.

ALTER TABLE security_alerts
  ADD COLUMN IF NOT EXISTS win_eventdata JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS wazuh_full_log JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS parent_process TEXT,
  ADD COLUMN IF NOT EXISTS parent_command_line TEXT,
  ADD COLUMN IF NOT EXISTS current_directory TEXT,
  ADD COLUMN IF NOT EXISTS integrity_level TEXT,
  ADD COLUMN IF NOT EXISTS process_guid TEXT,
  ADD COLUMN IF NOT EXISTS parent_process_guid TEXT,
  ADD COLUMN IF NOT EXISTS logon_id TEXT,
  ADD COLUMN IF NOT EXISTS logon_guid TEXT,
  ADD COLUMN IF NOT EXISTS hashes_raw TEXT,
  ADD COLUMN IF NOT EXISTS hash_md5 TEXT,
  ADD COLUMN IF NOT EXISTS hash_sha256 TEXT,
  ADD COLUMN IF NOT EXISTS hash_imphash TEXT,
  ADD COLUMN IF NOT EXISTS process_id TEXT,
  ADD COLUMN IF NOT EXISTS parent_process_id TEXT,
  ADD COLUMN IF NOT EXISTS user_sid TEXT;

CREATE INDEX IF NOT EXISTS idx_security_alerts_hash_sha256_col
  ON security_alerts (hash_sha256)
  WHERE hash_sha256 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_security_alerts_process_guid
  ON security_alerts (process_guid)
  WHERE process_guid IS NOT NULL;

COMMENT ON COLUMN security_alerts.win_eventdata IS
  'Structured data.win.eventdata / Sysmon fields extracted at ingest.';
COMMENT ON COLUMN security_alerts.wazuh_full_log IS
  'Wazuh full_log payload (text or structured) for legacy regex fallback.';
