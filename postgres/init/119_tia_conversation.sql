-- 119: TIA conversation state, bound pending actions, verified dashboard commands, turn timings.
--
-- Additive only. Nothing here changes an existing table. Rolling back application code
-- leaves these tables in place and harmless.
--
-- Scope and access:
--   * These tables are staff-only working state for the SOC console (platform_admin,
--     soc_manager, soc_analyst). They are never read by customer APIs.
--   * Every row is owned by one operator and one browser session. Application queries
--     always filter by operator, and a conversation is bound to one tenant scope (or to
--     the platform scope when tenant_id is NULL). A tenant switch starts a new
--     conversation, so pending actions cannot leak across customers.
--   * Row-level security is NOT enabled: tenant_id is nullable (platform scope) and the
--     tables hold no customer evidence, only identifiers, short summaries and timings.
--
-- Semantics worth stating once:
--   tia_pending_actions   a proposed action waiting for the operator's answer. Bound to
--                         action type, exact target, tenant scope, session and expiry.
--   tia_ui_commands       an instruction for the dashboard (for example open a case).
--                         'issued' means the server asked; only 'acknowledged' means the
--                         dashboard reported that the correct page loaded.

CREATE TABLE IF NOT EXISTS tia_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_email TEXT NOT NULL,
    operator_id UUID,
    session_id TEXT NOT NULL,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    selected_alert_id UUID REFERENCES security_alerts(id) ON DELETE SET NULL,
    -- Ordered alert ids from the last listing ("the first one", "the second one").
    referenced_alert_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_listing JSONB NOT NULL DEFAULT '{}'::jsonb,
    active_job_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    turn_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '8 hours')
);
CREATE INDEX IF NOT EXISTS idx_tia_conversations_owner
    ON tia_conversations (operator_email, session_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS tia_conversation_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES tia_conversations(id) ON DELETE CASCADE,
    turn_no INTEGER NOT NULL,
    -- Client-generated id; a retry or reconnect with the same id returns the stored
    -- response instead of executing the turn again.
    client_turn_id TEXT,
    request_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('operator', 'tia')),
    text TEXT NOT NULL,
    tool_name TEXT,
    tool_args JSONB NOT NULL DEFAULT '{}'::jsonb,
    tool_ok BOOLEAN,
    response JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, turn_no)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tia_turns_client_turn
    ON tia_conversation_turns (conversation_id, client_turn_id)
    WHERE client_turn_id IS NOT NULL AND role = 'operator';

CREATE TABLE IF NOT EXISTS tia_pending_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES tia_conversations(id) ON DELETE CASCADE,
    operator_email TEXT NOT NULL,
    session_id TEXT NOT NULL,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    target JSONB NOT NULL,
    summary TEXT NOT NULL,
    risk_class TEXT NOT NULL CHECK (risk_class IN ('navigation', 'read', 'write', 'disruptive')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'executed', 'expired', 'cancelled', 'refused')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    resolution TEXT
);
CREATE INDEX IF NOT EXISTS idx_tia_pending_live
    ON tia_pending_actions (conversation_id, created_at DESC) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS tia_ui_commands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES tia_conversations(id) ON DELETE CASCADE,
    pending_action_id UUID REFERENCES tia_pending_actions(id) ON DELETE SET NULL,
    operator_email TEXT NOT NULL,
    session_id TEXT NOT NULL,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    command_type TEXT NOT NULL CHECK (command_type IN ('open_case', 'open_review_item')),
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'issued'
        CHECK (status IN ('issued', 'acknowledged', 'failed', 'expired')),
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deliver_by TIMESTAMPTZ NOT NULL,
    acknowledged_at TIMESTAMPTZ,
    ack_payload JSONB,
    failure_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_tia_ui_commands_open
    ON tia_ui_commands (session_id, issued_at DESC) WHERE status = 'issued';

-- Correlated stage timings for each turn. Numbers and identifiers only: no operator
-- text, no evidence, no credentials.
CREATE TABLE IF NOT EXISTS tia_turn_timings (
    id BIGSERIAL PRIMARY KEY,
    request_id TEXT NOT NULL,
    conversation_id TEXT,
    turn_id TEXT,
    job_id TEXT,
    path TEXT NOT NULL,                 -- navigation | status | connector | model | deep
    ok BOOLEAN NOT NULL,
    total_ms NUMERIC(12, 2) NOT NULL,
    stages JSONB NOT NULL DEFAULT '{}'::jsonb,
    client_stages JSONB NOT NULL DEFAULT '{}'::jsonb,
    clock_offset_ms NUMERIC(12, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tia_turn_timings_recent ON tia_turn_timings (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tia_turn_timings_request ON tia_turn_timings (request_id);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mssp_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            tia_conversations, tia_conversation_turns, tia_pending_actions, tia_ui_commands, tia_turn_timings
            TO mssp_app;
        GRANT USAGE, SELECT ON SEQUENCE tia_turn_timings_id_seq TO mssp_app;
    END IF;
END
$$;

COMMENT ON TABLE tia_ui_commands IS
    'Dashboard commands. issued = the server asked; acknowledged = the dashboard reported the correct page loaded.';

INSERT INTO tia_schema_version (component, version) VALUES ('tia_conversation', 119)
ON CONFLICT (component) DO UPDATE SET version = GREATEST(tia_schema_version.version, EXCLUDED.version);
