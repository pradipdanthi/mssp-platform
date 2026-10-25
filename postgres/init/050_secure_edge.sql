-- KB-114: NikTiar Secure Edge add-on (WAF appliance inventory + entitlement flag)

CREATE TABLE IF NOT EXISTS secure_edge_nodes (
    hostname TEXT PRIMARY KEY,
    tenant_short_code TEXT,
    status TEXT NOT NULL DEFAULT 'online',
    version TEXT,
    capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE tenant_entitlements
  ADD COLUMN IF NOT EXISTS secure_edge_enabled BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN tenant_entitlements.secure_edge_enabled IS
  'Optional Secure Edge (self-hosted WAF/bot) add-on — available on any tier.';
