-- KB-114b: Secure Edge hybrid multi-tenant (shared SMB edge + dedicated enterprise)

ALTER TABLE secure_edge_nodes
  ADD COLUMN IF NOT EXISTS deployment_mode TEXT NOT NULL DEFAULT 'shared'
    CHECK (deployment_mode IN ('shared', 'dedicated')),
  ADD COLUMN IF NOT EXISTS appliance_token TEXT,
  ADD COLUMN IF NOT EXISTS last_config_version INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS secure_edge_sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_short_code TEXT NOT NULL,
    public_hostname TEXT NOT NULL,
    origin_url TEXT NOT NULL,
    -- NULL = eligible for any shared edge; set = pin to dedicated/shared node hostname
    edge_node_hostname TEXT,
    waf_profile TEXT NOT NULL DEFAULT 'standard',
    tls_mode TEXT NOT NULL DEFAULT 'off'
      CHECK (tls_mode IN ('off', 'http_only', 'acme')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (public_hostname)
);

CREATE INDEX IF NOT EXISTS idx_secure_edge_sites_tenant
  ON secure_edge_sites (tenant_short_code);

CREATE INDEX IF NOT EXISTS idx_secure_edge_sites_edge
  ON secure_edge_sites (edge_node_hostname);

CREATE TABLE IF NOT EXISTS secure_edge_events (
    id BIGSERIAL PRIMARY KEY,
    tenant_short_code TEXT,
    edge_hostname TEXT NOT NULL,
    public_hostname TEXT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    summary TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_secure_edge_events_created
  ON secure_edge_events (created_at DESC);

COMMENT ON TABLE secure_edge_sites IS
  'Hybrid Secure Edge: shared nodes host many tenants by Host/SNI; dedicated nodes pin one tenant.';
