-- KB-074: Customer organization profile fields on tenants (contact + address).
-- Idempotent for live apply.

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS primary_contact_name TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS primary_contact_email TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS primary_contact_phone TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS secondary_contact_name TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS secondary_contact_email TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS secondary_contact_phone TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS billing_email TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS address_line1 TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS address_line2 TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS city TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS state_region TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS postal_code TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS country TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS website TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS industry TEXT;

CREATE INDEX IF NOT EXISTS idx_tenants_country ON tenants (country);
CREATE INDEX IF NOT EXISTS idx_tenants_primary_contact_email ON tenants (primary_contact_email);
