-- KB-016: Appliance Registration and Heartbeat Receiver Foundation (schema
-- additions)
--
-- IMPORTANT: PostgreSQL only runs files in postgres/init/ automatically the
-- first time it initializes a brand-new, empty data volume. It will NOT
-- automatically apply to the existing mssp-postgres database, because that
-- database already has data in it. This file exists so any FUTURE fresh
-- install gets these changes automatically. For the already-running
-- environment, apply the same change using
-- scripts/kb016_create_appliance_registration_heartbeat.sh instead, which
-- runs the equivalent statements directly against the live database.
--
-- Changes:
--   1. Adds four nullable columns to appliances to support a durable,
--      appliance-presented API key for the heartbeat receiver
--      (POST /appliance/heartbeat):
--        - appliance_api_key_hash TEXT       (SHA-256 hex digest only -
--          the raw key is never stored, see backend-api/app/services/
--          appliance_auth_service.py)
--        - appliance_api_key_hint TEXT       (safe, display-only suffix)
--        - appliance_key_created_at TIMESTAMPTZ
--        - appliance_key_last_used_at TIMESTAMPTZ
--      All four are nullable so existing appliance rows (e.g. any created
--      directly via SQL before KB-016, such as KB-015's own validation
--      fixtures) are never broken by this change - a NULL
--      appliance_api_key_hash simply means that appliance cannot
--      authenticate a heartbeat yet, until it is (re-)registered through
--      POST /appliance/register.
--   2. Adds a UNIQUE constraint on appliance_api_key_hash, mirroring the
--      existing UNIQUE constraint already on
--      appliance_activation_tokens.token_hash.
--
-- This script is idempotent and safe to run more than once.

ALTER TABLE appliances ADD COLUMN IF NOT EXISTS appliance_api_key_hash TEXT;
ALTER TABLE appliances ADD COLUMN IF NOT EXISTS appliance_api_key_hint TEXT;
ALTER TABLE appliances ADD COLUMN IF NOT EXISTS appliance_key_created_at TIMESTAMPTZ;
ALTER TABLE appliances ADD COLUMN IF NOT EXISTS appliance_key_last_used_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'appliances_appliance_api_key_hash_key'
    ) THEN
        ALTER TABLE appliances
            ADD CONSTRAINT appliances_appliance_api_key_hash_key UNIQUE (appliance_api_key_hash);
    END IF;
END $$;
