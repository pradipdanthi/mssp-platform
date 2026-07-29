-- KB-086: Per-tenant Linux agent install tokens (headless one-liner install).

CREATE TABLE IF NOT EXISTS tenant_agent_install_tokens (
    tenant_id UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    install_token TEXT NOT NULL UNIQUE,
    linux_published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    rotated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tenant_agent_install_tokens_token
    ON tenant_agent_install_tokens (install_token);

DROP TRIGGER IF EXISTS trg_tenant_agent_install_tokens_updated_at ON tenant_agent_install_tokens;
CREATE TRIGGER trg_tenant_agent_install_tokens_updated_at
BEFORE UPDATE ON tenant_agent_install_tokens
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
