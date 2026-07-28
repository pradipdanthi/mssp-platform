-- KB-075: Contract-ready MSSP customer onboarding fields (commercial + capacity).
-- Idempotent for live apply.

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS legal_name TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS tax_id TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS contract_reference TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS contract_start_date DATE;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS contract_end_date DATE;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS licensed_endpoints INTEGER;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS data_residency TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS preferred_language TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS company_size TEXT;

CREATE INDEX IF NOT EXISTS idx_tenants_contract_reference ON tenants (contract_reference);
CREATE INDEX IF NOT EXISTS idx_tenants_tax_id ON tenants (tax_id);

COMMENT ON COLUMN tenants.legal_name IS 'Registered / legal entity name (may differ from display name)';
COMMENT ON COLUMN tenants.tax_id IS 'Tax / GST / VAT / EIN identifier';
COMMENT ON COLUMN tenants.contract_reference IS 'MSA / SOW / order form reference';
COMMENT ON COLUMN tenants.licensed_endpoints IS 'Contracted endpoint / agent seat count';
COMMENT ON COLUMN tenants.data_residency IS 'Preferred data residency region for the customer';
