-- KB-114c: Cloudflare-parity zone security settings for Secure Edge

ALTER TABLE secure_edge_sites
  ADD COLUMN IF NOT EXISTS zone_settings JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN secure_edge_sites.zone_settings IS
  'Cloudflare-like per-zone security: waf, firewall, rate_limit, ssl, cache, page_rules';

CREATE TABLE IF NOT EXISTS secure_edge_custom_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_short_code TEXT,
    edge_node_hostname TEXT,
    name TEXT NOT NULL,
    description TEXT,
    expression TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'block'
      CHECK (action IN ('block', 'challenge', 'allow', 'log', 'js_challenge')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INT NOT NULL DEFAULT 100,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_secure_edge_custom_rules_tenant
  ON secure_edge_custom_rules (tenant_short_code);

CREATE TABLE IF NOT EXISTS secure_edge_global_settings (
    edge_hostname TEXT PRIMARY KEY,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
