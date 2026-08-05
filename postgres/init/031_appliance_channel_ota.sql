-- Track-4: appliance channel inbox (cloud→appliance frames) + OTA offer tracking.
-- Additive only.

CREATE TABLE IF NOT EXISTS appliance_channel_inbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appliance_id UUID NOT NULL REFERENCES appliances(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    frame_type TEXT NOT NULL
        CHECK (frame_type IN (
            'control', 'ack', 'ota.offer', 'license.push', 'job', 'heartbeat', 'status', 'alert.meta'
        )),
    envelope JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'delivered', 'acked', 'failed', 'expired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ,
    acked_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '48 hours')
);

CREATE INDEX IF NOT EXISTS idx_appliance_channel_inbox_pending
    ON appliance_channel_inbox (appliance_id, status, created_at)
    WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS appliance_channel_outbound (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appliance_id UUID NOT NULL REFERENCES appliances(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    frame_type TEXT NOT NULL,
    envelope JSONB NOT NULL DEFAULT '{}'::jsonb,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_appliance_channel_outbound_appliance
    ON appliance_channel_outbound (appliance_id, received_at DESC);

COMMENT ON TABLE appliance_channel_inbox IS
    'Cloud→appliance channel frames (Phase B). Delivered via WSS or HTTPS poll.';
