-- Phase 3 AI SOC Triage: persist Tier-1 verdict/queue for fast list filters.
-- Populated on triage write (not on list load). Default list excludes ai_queue=low_priority.

ALTER TABLE security_alerts
  ADD COLUMN IF NOT EXISTS ai_verdict TEXT,
  ADD COLUMN IF NOT EXISTS ai_confidence NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS ai_queue TEXT,
  ADD COLUMN IF NOT EXISTS ai_auto_closed BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS ai_resolution_label TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'security_alerts_ai_verdict_check'
  ) THEN
    ALTER TABLE security_alerts
      ADD CONSTRAINT security_alerts_ai_verdict_check
      CHECK (
        ai_verdict IS NULL
        OR ai_verdict IN ('BENIGN_FALSE_POSITIVE', 'SUSPICIOUS', 'MALICIOUS')
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'security_alerts_ai_queue_check'
  ) THEN
    ALTER TABLE security_alerts
      ADD CONSTRAINT security_alerts_ai_queue_check
      CHECK (
        ai_queue IS NULL
        OR ai_queue IN ('low_priority')
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'security_alerts_ai_confidence_check'
  ) THEN
    ALTER TABLE security_alerts
      ADD CONSTRAINT security_alerts_ai_confidence_check
      CHECK (
        ai_confidence IS NULL
        OR (ai_confidence >= 0 AND ai_confidence <= 100)
      );
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_security_alerts_ai_queue
  ON security_alerts (ai_queue)
  WHERE ai_queue IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_security_alerts_ai_verdict
  ON security_alerts (ai_verdict, ai_confidence)
  WHERE ai_verdict IS NOT NULL;

COMMENT ON COLUMN security_alerts.ai_verdict IS
  'Tier-1 Ollama verdict persisted on triage write for list filters.';
COMMENT ON COLUMN security_alerts.ai_confidence IS
  'Tier-1 confidence 0-100 persisted on triage write.';
COMMENT ON COLUMN security_alerts.ai_queue IS
  'low_priority when BENIGN_FALSE_POSITIVE and confidence >= 85; else null (actionable).';
COMMENT ON COLUMN security_alerts.ai_auto_closed IS
  'True only when ENABLE_AUTO_CLOSE_LOW_RISK gated auto-close ran successfully.';
COMMENT ON COLUMN security_alerts.ai_resolution_label IS
  'Human-readable AI resolution label e.g. Closed (AI Auto-Triage); status stays closed/false_positive.';
