-- Tier-1 AI SOC Triage Copilot: cache Ollama verdicts by alert + payload hash.
-- On-demand only (detail drawer); never blocks alert list loads.

CREATE TABLE IF NOT EXISTS alert_ai_triage_cache (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  alert_id        UUID NOT NULL REFERENCES security_alerts(id) ON DELETE CASCADE,
  tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  content_hash    TEXT NOT NULL,
  model           TEXT,
  verdict         TEXT NOT NULL,
  confidence      NUMERIC(5,2) NOT NULL,
  summary         TEXT NOT NULL,
  recommended_action TEXT NOT NULL,
  suggested_suppression_scope JSONB NOT NULL DEFAULT '{}'::jsonb,
  raw_response    JSONB,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT alert_ai_triage_cache_verdict_check
    CHECK (verdict IN ('BENIGN_FALSE_POSITIVE', 'SUSPICIOUS', 'MALICIOUS')),
  CONSTRAINT alert_ai_triage_cache_action_check
    CHECK (recommended_action IN ('AUTO_SUPPRESS', 'INVESTIGATE_HOST', 'ISOLATE_AGENT')),
  CONSTRAINT alert_ai_triage_cache_confidence_check
    CHECK (confidence >= 0 AND confidence <= 100)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_ai_triage_cache_alert_hash
  ON alert_ai_triage_cache (alert_id, content_hash);

CREATE INDEX IF NOT EXISTS idx_alert_ai_triage_cache_tenant
  ON alert_ai_triage_cache (tenant_id, updated_at DESC);

COMMENT ON TABLE alert_ai_triage_cache IS
  'Cached Tier-1 Ollama triage (verdict/confidence/summary/action/suppress scope); keyed by alert_id + content hash.';
