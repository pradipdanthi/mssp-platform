-- KB-071b: Roadmap entitlement modules (NTA / Threat Intel / Endpoint Forensics)
-- Additive — safe to re-run. Vulnerability Management column already exists.
ALTER TABLE tenant_entitlements
  ADD COLUMN IF NOT EXISTS zeek_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS misp_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS velociraptor_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS roadmap_notes TEXT;
