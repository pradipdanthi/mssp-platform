-- KB-079b: Track automated vulnerability scan cadence per tenant (scheduler).
BEGIN;

ALTER TABLE tenant_entitlements
    ADD COLUMN IF NOT EXISTS last_vuln_scan_at TIMESTAMPTZ;

COMMIT;
